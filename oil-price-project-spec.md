# 全国城市油价自动采集项目：AI 实施说明

## 1. 如何使用本文档

创建一个空项目，把本文档交给负责开发的 AI，并发送：

> 请按本文档完整实现项目，而不只是给出计划。先验证网站结构，再开发采集器、测试、数据文件和 GitHub Actions。完成一次真实采集，说明实际覆盖情况与缺失项。不要编造城市价格或预测。未经我明确授权，不要创建远程仓库或推送；需要我操作的 GitHub 设置请逐步列出。

默认项目名：`china-city-oil-prices`。

目标：使用 GitHub Actions 定时采集汽油价格网，结果提交回同一仓库，每个省级行政区一个 JSON 文件，供其他项目读取。不要求常驻服务器。

本文是实施要求，不代表采集程序或远程部署已经完成。

## 2. 范围和事实边界

- 主要数据源：<http://www.qiyoujiage.com/>。
- 覆盖目标：中国大陆 31 个省级行政区，以及网站实际提供的城市、自治州等地级查询页面。
- 采集 92 号、95 号、98 号汽油和 0 号柴油的元/升价格。
- 保存下次调价时间、下次预估方向，以及有可靠依据时的各油品下次价格。
- 本项目不是官方 API，数据不是加油站实时成交价。
- 城市/州页面的单组价格不代表该行政区内所有县区、站点的价格均相同。
- 不得把省级价格复制给缺失城市，制造“全国城市全覆盖”。
- 98 号或其他油品缺失时保留 `null`，不可套用其他地区或标号的价格。
- 不得根据经验密度把标准品吨价换算成具体标号零售价。

2026-11-09 曾成功访问的页面如下。开发时必须再次验证，不把历史验证当成永久有效：

| 地区 | 页面 |
|---|---|
| 四川省级 | <http://www.qiyoujiage.com/sichuan.shtml> |
| 成都 | <http://www.qiyoujiage.com/sichuan/chengdu.shtml> |
| 甘孜 | <http://www.qiyoujiage.com/sichuan/ganzi.shtml> |
| 阿坝 | <http://www.qiyoujiage.com/sichuan/aba.shtml> |
| 凉山 | <http://www.qiyoujiage.com/sichuan/liangshan.shtml> |
| 绵阳 | <http://www.qiyoujiage.com/sichuan/mianyang.shtml> |
| 深圳 | <http://www.qiyoujiage.com/guangdong/shenzhen.shtml> |
| 昆明 | <http://www.qiyoujiage.com/yunnan/kunming.shtml> |

当时页面确实提供城市差异价格。例如成都和甘孜价格不同。因此必须抓城市页面，不能只抓省级页面。

## 3. 技术方案与目录

优先使用 Python 3.15（与开发机一致）、`requests`、`beautifulsoup4` 和标准库 `unittest`。不默认引入浏览器、数据库、Web 后端或大模型 OCR。

开发时选择并锁定兼容的依赖版本，禁止把猜测的版本号写成已验证版本。

建议目录：

```text
.github/workflows/update-oil-prices.yml
src/oil_prices/__init__.py
src/oil_prices/__main__.py
src/oil_prices/fetcher.py
src/oil_prices/parser.py
src/oil_prices/collector.py
config/regions.json
data/provinces/四川省-510000.json
data/provinces/广东省-440000.json
data/index.json
data/status.json
tests/test_parser.py
tests/test_collector.py
tests/fixtures/
requirements.txt
README.md
```

允许按实际复杂度合并模块，避免无意义的抽象。省级文件使用六位行政区代码命名，防止中文路径及拼音歧义。README 提供代码与中文名称对应关系。

必须支持在项目根目录执行：

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m src.oil_prices --province 510000
python -m src.oil_prices
```

其中省份选择用于本地针对性验证，默认命令采集所有已配置地区。

## 4. 来源发现与城市清单

### 4.1 开发前先调查

检查首页、省级页、城市页的原始 HTML、实际链接、页面标题和价格标签。不要因简化后的网页正文没有城市链接，就断言网站不存在城市页。

先确认站点使用条款、robots.txt 和采集限制。robots.txt 返回 404 不代表获得无限制访问或再发布授权。只处理公开数据，不绕过验证码、登录、限流或访问控制。

如 HTTPS 可用，优先使用；如只能 HTTP，明确记录传输未加密，不发送任何凭据或敏感数据。

### 4.2 清单维护规则

`config/regions.json` 是受版本控制的采集清单，至少保存：

- 省级代码、名称、源页面地址。
- 城市/州代码、名称、源页面地址。
- 来源发现依据，以及链接是否已经实测。
- 源站没有对应页面的地区及原因。

省级链接优先从首页实际链接发现，不能假设拼音规则统一。例如山西和陕西在源站可能使用不同的特殊路径。

城市链接优先从站内导航、公开站点地图或其他实际公开链接发现。如果站点没有完整索引：

1. 使用可溯源、允许使用的行政区划清单列出预期城市，记录清单日期和来源。
2. 人工或开发阶段受控确认候选 URL，每个候选只做有限验证，不枚举大量可能拼音。
3. 人工确认页面对应地区；采集时信任配置 URL，只验证 HTTP 状态、价格标签与返回内容，不比较网页地区名称与配置名称。
4. 把验证通过的链接写入清单；定时任务不重复进行搜索引擎检索和大规模路径试探。

直辖市按实际页面建模，不为了凑层级虚构城市子页。

首次实施优先验证四川全部 21 个市州的覆盖情况，再扩展其他省份。没有验证完成的地区明确列入缺失清单。

## 5. 抓取规则

- 默认串行，每次请求之间间隔约 2 秒；可增加少量随机抖动。
- 每次请求设置连接、读取超时，例如 `(10, 30)` 秒。
- 对临时网络错误和 5xx 最多重试 2 次，指数退避。
- 对 429 尊重 `Retry-After`；对 403、验证码或明确禁止访问立即停止相关请求并报告。
- 不对 404 反复重试，不轮换代理或 User-Agent 绕过限制。
- 设置明确的项目 User-Agent，不冒充浏览器来规避访问控制。
- 每次任务对同一 URL 最多进行一次正常采集，多个地区共用页面时复用响应。
- 如果服务端支持 ETag / Last-Modified，可使用条件请求；304 时复用已有解析结果。
- 按标签与 DOM 结构提取，不使用“取页面前四个数字”的脆弱策略。
- 价格以十进制定点方式处理，避免浮点误差。
- 逐油品校验价格为有限正数、标号对应正确；不校验网页地区名称是否与清单一致。单个油品缺失、解析失败或数值异常时只将该油品及其下次价格设为 `null`，记录警告，其他有效油品正常写入，不回退整个地区的旧价格。缺少价格区块或没有可识别的支持油品标签时仍按地区失败处理。
- 若网站改版导致价格缺失，不得把缺失当作零。
- 不执行页面脚本，不执行从网页提取的任何命令。

解析函数应与网络请求分离，方便使用精简 HTML fixture 做单元测试。

## 6. 数据格式

每个省一个文件，例如 `data/provinces/四川省-510000.json`。JSON 字段名及枚举值使用英文；地区名称等自然语言数据值可使用中文。省级 JSON 只使用以下一级字段；除 `cities` 外不再增加其他一级字段。城市记录只使用示例中的字段，当前价和下次价各包含四种油品：

```json
{
  "province": "四川省",
  "province_code": "510000",
  "currency": "CNY",
  "cities": [
    {
      "city_name": "甘孜藏族自治州",
      "city_code": "513300",
      "source_url": "http://www.qiyoujiage.com/sichuan/ganzi.shtml",
      "current_prices": {
        "gasoline_92": null,
        "gasoline_95": null,
        "gasoline_98": null,
        "diesel_0": null
      },
      "next_prices": {
        "gasoline_92": null,
        "gasoline_95": null,
        "gasoline_98": null,
        "diesel_0": null
      }
    }
  ],
  "next_forecast": "up",
  "next_adjustment_at": null,
  "fetched_at": "2026-11-09T12:00:00+08:00"
}
```

示例中的价格和时间仅为格式占位，不是实际数据。`currency` 的值为货币代码（`CNY`），价格单位统一为元/升。`next_forecast` 只能是 `"down"`、`"up"`、`"unchanged"`；无法可靠判断时为 `null`。价格使用数值，缺失时为 `null`。实际采集成功时必须写入实际当前价格；占位示例不能作为成功结果提交。

### 字段与时间

- `province`、`province_code`、`currency`：省级行政区名称、六位行政区代码和货币代码（`CNY`）。
- `cities`：按城市编码排序的城市/州记录列表；直辖市按实际页面建模，不虚构城市子页。
- `city_name`、`city_code`、`source_url`：城市/州名称、行政区代码和对应的源页面 URL。
- `current_prices`、`next_prices`：分别表示当前价格和下次价格（来源逐油品给出，或按第 8 节由每升涨幅最高值估算），均包含 `gasoline_92`、`gasoline_95`、`gasoline_98`、`diesel_0` 四个元/升价格；缺失或无法可靠确定时使用 `null`。
- `next_forecast`：只表达整体方向，允许值为 `"down"`、`"up"`、`"unchanged"` 或 `null`，不表示逐油品官方预测。
- `next_adjustment_at`：可靠解析的北京时间 ISO 8601 时间；不能确定时使用 `null`。
- `fetched_at`：本省数据本次成功采集的北京时间 ISO 8601 时间；每次本省采集成功时更新，因此即使价格未变，省文件也可能产生时间戳差异。

`data/status.json` 保存本轮开始/结束时间、总体状态、各地区最后尝试时间、最后成功时间、错误和是否使用旧数据。`fetched_at` 记录在各省 JSON 中；状态文件可记录任务级状态。成功时间更新允许产生每日状态提交，但不可声称“完全没变化就绝不提交”。

统一省价（`uniform_pricing: true`）只请求省级页面，`data/status.json` 只以省代码记录一条状态，不展示下属城市。`data/index.json` 中这类省份只记录省级页面状态，不输出 `expected_cities`、`successful_cities`、`missing_cities`。非统一省价继续逐城市采集并记录城市状态和覆盖统计。

配置中统一省价的省份保留省级名称、代码及 URL，`cities` 为空数组，不列出下属城市名称、代码或 URL。当前配置包含 21 个统一省价省份，以及其余 10 个省份的 125 个城市记录。

`data/index.json` 保存所有省文件的相对地址、成功城市数、预期城市数、缺失城市列表。覆盖统计必须基于清单计算，区分“已有配置全部成功”和“全国覆盖完整”。

所有 JSON 键名必须使用英文并符合上述结构，不得为省级数据新增其他一级字段。JSON 必须 UTF-8、稳定缩进、稳定排序；城市按编码排序，减少无意义 diff。

## 7. 下次调价时间解析

页面可能写“11月12日24时调整”，而未给年份。

- 时区固定为北京时间 `Asia/Shanghai`。
- “11月12日24时”应规范化为“11月13日00:00:00+08:00”。
- 优先依据页面明确日期确定年份；仅有月日时允许结合北京时间抓取日期推断。
- 推断需使用合理的临近日期窗口，例如前后 45 天。不要把已经过期的本月日期自动变成明年同一天。
- 跨年要测试，例如 12 月查询 1 月调整日期。
- 日期与上下文不一致、过期或无法消除歧义时将 `next_adjustment_at` 设为 `null`，并输出告警。
- 不可以把抓取时间当作价格生效时间。

## 8. 下次预估与价格规则：区分整体方向与逐油品价格

页面可能只公布：

> 预计上调 90 元/吨，约 0.07 元/升至 0.08 元/升。

该描述只能用于填写整体 `next_forecast: "up"`，不是 92、95、98 和柴油各自的预测，不能伪装成逐油品官方结果。

### 必须实现

1. 从来源判断整体下次方向，`next_forecast` 仅能写 `"down"`、`"up"` 或 `"unchanged"`；无法明确判断时写 `null`。
2. 只有来源明确提供某城市各油品的下次价格，且标签与地区均已核实，才写入对应 `next_prices` 数值。
3. 页面只给出不分油品的每升涨幅范围（如 0.07 元/升至 0.08 元/升）时，`next_prices` 按“当前价 + 范围最高值”估算：四种油品使用同一涨跌额，结果保留两位小数。这是用户确认的估算规则，不是官方逐油品预测。
4. 不根据每吨涨跌额使用密度公式换算；只使用页面直接给出的每升范围。
5. 下次调价日期不明、已过期、方向不明（非 `up`/`down`）或来源解析失败时，`next_prices` 保持 `null`；方向为 `unchanged` 时同样保持 `null`。

`next_forecast` 给出方向；有每升范围且调价日期有效时，`next_prices` 为估算值。README 和数据必须说明：下次价格为估算，不是正式调价，也不是加油站成交价。

## 9. 数据可靠性与失败策略

- 首次采集失败的城市：不生成假价格，进入覆盖缺失和错误清单。
- 曾经成功、当前失败的城市：保留上一份价格，状态标记 `stale`，注明最后成功时间和错误。
- 单城市失败不得清空整个省文件。
- 省份、城市解析结果全部校验完成后，使用临时文件与原子替换写入。
- 对重复城市代码、错误省市归属、返回首页、空白页和异常重定向报错。
- 网络重定向限制在明确允许的源站域名范围，禁止请求内网或任意第三方地址。
- 页面中出现 HTML/脚本内容时只作为不可信文本处理，不能注入 workflow 或 shell。
- 部分失败时允许保存成功结果和状态文件，但进程最终以非零码退出，让 Actions 显示失败。
- 发生源站全局封禁或限流时停止后续抓取，不继续请求数百次。

## 10. GitHub Actions

工作流至少支持手动执行和每天定时运行。参考配置如下，开发 AI 应结合真实实现核验：

```yaml
name: Update oil prices

on:
  workflow_dispatch:
  schedule:
    - cron: "23 2 * * *"

permissions:
  contents: write

concurrency:
  group: update-oil-prices
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.15"
          cache: pip

      - name: Install dependencies
        run: python -m pip install -r requirements.txt

      - name: Run targeted unit tests
        run: python -m unittest discover -s tests -v

      - name: Collect data
        id: collect
        continue-on-error: true
        run: python -m src.oil_prices

      - name: Commit generated data
        if: ${{ !cancelled() && steps.collect.outcome != 'skipped' }}
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -- data/
          if git diff --cached --quiet; then
            echo "No data changes"
            exit 0
          fi
          git commit -m "chore: update oil prices"
          git push

      - name: Report collection failure
        if: ${{ !cancelled() && steps.collect.outcome == 'failure' }}
        run: |
          echo "::error::Collection was incomplete. Check data/status.json and logs."
          exit 1
```

说明：

- 示例 UTC `02:23` 对应北京时间 `10:23`，每天一次。手动运行可用于调价日补采。
- 不承诺调价时刻实时更新；GitHub 定时任务可能延迟。
- 不默认每小时访问全国数百页面；先测量任务耗时与请求数，遵守源站规则。
- `timeout-minutes` 必须结合实际城市数、节流和重试预算验证。超预算应调整，不得通过取消限速来赶时间。
- 推荐在实施时核查 action 版本，并按项目策略固定到可信的完整提交 SHA。
- 只使用仓库自带的 `GITHUB_TOKEN`，普通场景不需要个人 PAT。
- 不把 token 写进代码、日志或生成的 JSON。
- 定时采集只在默认分支执行，不让来自不可信 PR 的代码获得写仓库权限。
- 若仓库或组织禁止直接推送，不能绕过分支保护；改为按现有规则提交数据 PR，或由用户选择专门数据分支并同步文档。
- 公开仓库长时间无活动可能被 GitHub 暂停定时任务，需检查 Actions 页面并按官方规则恢复；不要承诺机器人提交一定避免暂停。
- Actions 使用额度以 GitHub 当前套餐为准，不能承诺无限免费。

## 11. GitHub 部署步骤

README 必须向用户提供以下可执行步骤：

1. 在 GitHub 创建空仓库，建议先公开以便访问 JSON；确认用户接受数据公开。
2. 在本地初始化并提交项目，或使用现有仓库，推送到默认分支。
3. 确认 Actions 已启用，组织策略允许所选 actions 运行。
4. 在仓库 Settings → Actions → General 检查 workflow 写权限；以实际组织策略为准。
5. 在 Actions 中手动执行 `Update oil prices`。
6. 检查任务最终结论、`data/status.json`、覆盖统计和实际数据提交，不只检查程序是否启动。
7. 再等一次定时触发，确认默认分支上的自动采集工作流实际运行。

默认通过 GitHub Raw 读取：

```text
https://raw.githubusercontent.com/<OWNER>/<REPO>/<BRANCH>/data/provinces/四川省-510000.json
```

若启用 GitHub Pages 并从默认分支根目录发布，预计地址为：

```text
https://<OWNER>.github.io/<REPO>/data/provinces/四川省-510000.json
```

Pages 是可选项。若要求自动提交后自动发布，不要假设 `GITHUB_TOKEN` 提交会再次触发另一个 push workflow；应把 Pages 官方 artifact 构建/部署接在同一个 workflow 中，授予 `pages: write`、`id-token: write` 并配置 `github-pages` environment。需在实施时核查 GitHub 当前官方 Pages 部署步骤。

若未实现 Pages 部署，只承诺 Raw 地址可用，不声称 Pages 已自动更新。说明 Raw/Pages 均可能存在缓存，且中国大陆访问速度不保证。

## 12. 测试与验收

仅针对本项目功能运行必要验证，不引入无关测试体系。

### 单元测试

- 四种油品按正确标签解析，布局空白变化不影响结果。
- 成都与甘孜 fixture 解析为不同价格，禁止省价覆盖城市价。
- 缺失 98 号时返回 `null` 并报告缺失，不制造数值。
- 缺少价格区块的 200 错误页或首页被拒绝；配置 URL 返回的有效价格不因地区标签名称不同而被拒绝。
- 价格以数值形式正确解析，缺失油品保持 `null`。
- 调价“24时”、跨年、过期预测、缺失年份的解析正确。
- 只有整体涨跌描述时正确填写方向，且不据此生成逐油品下次价格。
- 来源没有明确方向时 `next_forecast` 为 `null`；缺失油品价格为 `null`。
- 一个城市失败时旧数据保留，其他成功城市正常更新，最终退出码非零。
- 相同业务输入不会改变价格或打乱排序；成功采集时更新时间戳属于预期变更。
- robots/访问控制、超时、限流的处理可通过模拟响应验证。

### 真实采集验收

1. 重新访问本文列出的 7 个城市/州样例，确认标签、来源、解析结果一致。
2. 生成四川省文件，列出 21 个市州各自的“成功/缺失/失败”，不得未经验证宣称全部覆盖。
3. 扩展至 31 省级行政区，生成实际覆盖报告；对没有页面的城市保留缺失理由。
4. 至少核验两个省的城市页面，防止解析器仅适用于四川。
5. 读取真实生成的 JSON，校验 schema、数值类型、日期、排序与去重。
6. 在 GitHub 托管运行器上手动执行成功，确认该运行器能够访问源站。
7. 确认结果实际提交到了仓库，并可通过 Raw 地址读取。
8. 如果设置了 Pages，实际访问发布 URL 并确认内容是最新提交的数据。
9. 若未能访问源站或覆盖不完整，明确交付限制，不能仅凭模拟测试宣称端到端部署完成。

测试 fixture 只保留解析需要的精简结构与事实数据，不复制完整网站页面、样式或文章。

## 13. 最终交付要求

开发 AI 完成后应交付：

1. 可运行的采集代码、依赖、单元测试。
2. 经实际验证的省市清单。
3. 一次真实采集生成的省级 JSON、索引、状态和覆盖统计。
4. GitHub Actions 工作流。
5. README：运行命令、部署步骤、字段含义、数据来源、更新频率、预测限制、失败排查和数据使用注意事项。
6. 明确列出未覆盖地区、不可验证信息，以及需要用户在 GitHub 上完成的步骤。

禁止：

- 只交付代码框架或伪数据，却称已完成。
- 未获授权就创建远程仓库或上传文件。
- 用省价批量填充城市，掩盖数据缺失。
- 把第三方参考价或非官方估算称为官方价格或确定的下期价格。
- 抓取受限内容或绕过网站访问控制。

建议先交付可靠的“现价 + 下次调价日期 + 下次预估方向”；只有来源对具体油品提供可靠下次价格时才填写对应价格。
