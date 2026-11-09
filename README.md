# china-city-oil-prices

Collects city-level gasoline and diesel prices from qiyoujiage.com and stores them as JSON under `data/`. A GitHub Actions workflow runs the collector once a day.

The data format and rules are described in [oil-price-project-spec.md](oil-price-project-spec.md).

## Requirements

- Python 3.15
- `pip install -r requirements.txt`

## Usage

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m src.oil_prices                 # all configured provinces
python -m src.oil_prices --province 510000
```

Exit codes: `0` all configured cities succeeded, `1` partial failure (stale data kept for failed cities), `2` run failed (site refused the request, or the host was not allowed).

## Configuration

`config/regions.json` lists provinces and their cities. The collector trusts the manually reviewed source URLs and does not compare price-label region names with the config. Existing `source_region_name` fields are retained for reference but are not used by the collector. Price-label format, supported grades and positive price values are still validated.

Each province has `uniform_pricing`. When it is `true`, only the province page is fetched. Both the config and province output have `cities: []`, with no city codes or URLs. When it is `false` (内蒙古, 辽宁, 黑龙江, 四川, 贵州, 云南, 西藏, 陕西, 青海, 新疆), each city is fetched separately. The config covers all 31 provinces, autonomous regions and municipalities: 21 uniform-price province records and 125 cities across the remaining 10 provinces. `code_verified` is `false` for every province; official GB/T 2260 code verification remains separate from manual source URL review. Pages that cannot be fetched or whose price data cannot be parsed show up as failed in `data/status.json` and `data/index.json`.

## Output

- `data/provinces/<province_name>-<province_code>.json`: prices and next-adjustment notice per province (for example `河北省-130000.json` or `内蒙古自治区-150000.json`). Use the index's `path` to locate files. Legacy code-only files are still read for previous prices and removed after the renamed file is written.
- `data/index.json`: province-page status; city coverage counts and missing cities are included only for non-uniform provinces.
- `data/status.json`: run times, per-region errors and stale flags. Uniform-price provinces have one entry keyed by province code (for example `130000`), with no city entries. Non-uniform provinces retain city entries. Uniform-price collection never requests city pages.

`next_prices` is an **estimate**, not an official price: when the notice gives a per-liter range (for example `0.07元/升-0.08元/升`), the collector adds (or subtracts, for a decrease) the highest value to each current price. It is `null` when the direction is `unchanged` or unknown, the adjustment date is past or missing, or no per-liter range is given. It is not the actual price at the pump.

Prices are parsed independently per grade. Missing, unparseable, non-positive or non-finite values become `null` for that grade only; valid prices are still written, and the affected grade's `next_prices` is also `null`. Invalid entries produce log warnings, not a whole-region failure or reuse of old prices. Missing price blocks or pages with no supported price labels still fail the region.

Each province output includes `next_adjustment_notice`, the province page's forecast text, for example `"目前预计上调油价90元/吨(0.07元/升-0.08元/升)"`. It includes the per-ton amount and bracketed per-liter range as provided, omits trailing reminders, and removes layout whitespace. Decrease and unchanged notices are also supported. A missing notice is `null` with a log warning; a failed province-page fetch preserves the previous notice.
