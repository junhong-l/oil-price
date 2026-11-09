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

`config/regions.json` lists provinces and their cities. Each city has a `source_region_name`, which must match the label prefix on the source page (for example `成都` in `成都92#汽油`). The config covers all 31 provinces, autonomous regions and municipalities (343 cities). The city codes and URL paths were written from memory and are not verified against an official GB/T 2260 list or the live site; `code_verified` is `false` for every province. The first Action run is the validation step: any city whose page does not exist or whose label does not match `source_region_name` shows up as failed in `data/status.json` and `data/index.json`, and should then be corrected in the config.

## Output

- `data/provinces/<province_code>.json`: prices and next-adjustment notice per province.
- `data/index.json`: per-province coverage and missing cities.
- `data/status.json`: run times, per-region errors and stale flags.

`next_prices` is an **estimate**, not an official price: when the notice gives a per-liter range (for example `0.07元/升-0.08元/升`), the collector adds (or subtracts, for a decrease) the highest value to each current price. It is `null` when the direction is `unchanged` or unknown, the adjustment date is past or missing, or no per-liter range is given. It is not the actual price at the pump.
