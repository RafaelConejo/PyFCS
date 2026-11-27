"""Summarize BOUNDED_SUM equivalence between PyFCS and Java; no membership recomputation.

Place in Source/test/cases/java_comparison/. Run from the project root:
    python -m Source.test.cases.java_comparison.analyze_java_results
Dependencies: Python >=3.9, matplotlib (for PNG/SVG figures only).
Use --no-plots for standard-library-only output.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath

REPORTS = Path(__file__).resolve().parent / 'reports'
MODES = ('bounded_sum',)
LABELS = {'bounded_sum': 'BOUNDED_SUM'}
FIELDS = ('mae', 'rmse', 'bias', 'max_error', 'within_tolerance_fraction',
          'active_count', 'active_mae')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-28)


def count(fraction, total):
    require(isinstance(fraction, (int, float)) and 0 <= fraction <= 1,
            'Invalid agreement fraction')
    value = fraction * total
    integer = round(value)
    require(abs(value - integer) < 1e-4, 'Agreement fraction does not yield an integer count')
    return integer


def load_pair(report_path, csv_path):
    report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    n = report['processed_samples']
    require(type(n) is int and 0 < n <= report['declared_samples'], 'Invalid sample count')
    require(not report['complete_file_validated'] or n == report['declared_samples'],
            'Complete report has inconsistent sample counts')
    require(0 < report['tolerance'] < 1, 'Invalid tolerance')
    require('bounded_sum' in report['modes'], 'Expected BOUNDED_SUM results')
    with csv_path.open(encoding='utf-8-sig', newline='') as f:
        csv_rows = list(csv.DictReader(f))
    rows = {}
    for r in csv_rows:
        if r['operator'] != 'bounded_sum':
            continue
        key = (r['operator'], r['category'])
        require(key not in rows, f'Duplicate CSV row: {key}')
        rows[key] = r
    categories = [r['category'] for r in report['modes']['bounded_sum']['per_category']]
    k = len(categories)
    require(k and len(set(categories)) == k, 'Invalid category labels')
    total = n*k
    require(set(rows) == {(m, c) for m in MODES for c in categories}, 'CSV category/operator mismatch')
    summaries, details = {}, []
    for mode in MODES:
        block = report['modes'][mode]
        ordered = block['per_category']
        require(len(ordered) == k and {r['category'] for r in ordered} == set(categories),
                f'JSON category mismatch: {mode}')
        for r in ordered:
            key = (mode, r['category'])
            for field in FIELDS:
                v = r[field]
                raw = rows[key][field]
                require((v is None and raw == '') or
                        (v is not None and float(raw) == v), f'JSON/CSV mismatch: {key}, {field}')
                require(v is None or math.isfinite(v), f'Non-finite statistic: {key}, {field}')
            require(type(r['active_count']) is int and 0 <= r['active_count'] <= n, 'Invalid active count')
            require(0 <= r['mae'] <= 1 and 0 <= r['rmse'] <= 1 and 0 <= r['max_error'] <= 1,
                    'Invalid error metric')
            require((r['active_count'] == 0) == (r['active_mae'] is None), 'Invalid active MAE')
            hits = count(r['within_tolerance_fraction'], n)
            details.append(dict(operator=mode, **r, comparisons=n,
                                within_tolerance_count=hits, outside_tolerance_count=n-hits))
        active = sum(r['active_count'] for r in ordered)
        hits = sum(count(r['within_tolerance_fraction'], n) for r in ordered)
        mae = math.fsum(r['mae'] for r in ordered)/k
        rmse = math.sqrt(math.fsum(r['rmse']**2 for r in ordered)/k)
        max_error = max(r['max_error'] for r in ordered)
        require(close(mae, block['mae']) and close(rmse, block['rmse']) and close(max_error, block['max_error']),
                f'Inconsistent global metrics: {mode}')
        require(hits == count(block['membership_within_tolerance_fraction'], total),
                f'Inconsistent global agreement: {mode}')
        active_mae = (math.fsum(r['active_count']*(r['active_mae'] or 0) for r in ordered)/active
                      if active else None)
        all_hits = count(block['samples_all_within_tolerance_fraction'], n)
        winner_hits = count(block['winner_set_agreement'], n)
        overlap_hits = count(block['winner_overlap_agreement'], n)
        w = block['worst']
        require(w['category'] in categories and 0 <= w['sample_index'] < n and
                close(w['absolute_error'], max_error) and
                close(abs(w['java']-w['pyfcs']), max_error), f'Invalid worst case: {mode}')
        summaries[mode] = dict(
            comparisons=total, samples=n, categories=k, mae=block['mae'], rmse=block['rmse'],
            max_error=max_error, bias=math.fsum(r['bias'] for r in ordered)/k,
            active_count=active, active_mae=active_mae,
            membership_within_tolerance_fraction=block['membership_within_tolerance_fraction'],
            membership_within_tolerance_count=hits, membership_outside_tolerance_count=total-hits,
            samples_all_within_tolerance_fraction=block['samples_all_within_tolerance_fraction'],
            samples_all_within_tolerance_count=all_hits, samples_outside_tolerance_count=n-all_hits,
            winner_set_agreement=block['winner_set_agreement'], winner_set_agreement_count=winner_hits,
            winner_overlap_agreement=block['winner_overlap_agreement'], winner_overlap_agreement_count=overlap_hits,
            worst=w)
    return report, categories, summaries, details


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def fmt(value):
    return 'N/A' if value is None else f'{value:.8g}'


def pct(value):
    return f'{100*value:.6f}%'


def name(path):
    return PureWindowsPath(path).name


def make_report(report, categories, summaries, details, provenance):
    n = report['processed_samples']; k = len(categories); total = n*k
    b = summaries['bounded_sum']
    lines = ['# PyFCS / Java — Bounded-sum membership equivalence', '',
             '## Experimental setup', '',
             f'- PyFCS model: `{name(report["model"])}`',
             f'- Model SHA-256: `{report["model_file_sha256"]}`',
             f'- Java evaluation file: `{name(report["evaluation"])}`',
             '- Aggregation: BOUNDED_SUM in PyFCS; Java reference numerically consistent with bounded sum.',
             f'- RGB samples: {n:,} of {report["declared_samples"]:,} declared; unique RGB count unavailable.',
             f'- Categories: {k}; membership comparisons: {total:,}.',
             f'- Seed: {report.get("seed")}; absolute tolerance: {report["tolerance"]:g}.',
             f'- Complete input validated: {report["complete_file_validated"]}.',
             f'- Engine: {report["engine"]}; fast/API checked maximum error: {fmt(report.get("fast_scalar_max_error"))}.',
             f'- Recorded processing time (original evaluation run): {report["seconds"]:.3f} s.', '',
             '## Global statistics', '', '| Metric | Result |', '|---|---:|']
    for label, field in [('MAE','mae'),('RMSE','rmse'),('Maximum absolute error','max_error'),
                         ('Mean signed error (PyFCS - Java)','bias'),('Active-membership MAE','active_mae')]:
        lines.append(f'| {label} | {fmt(b[field])} |')
    for label, field in [('Active membership comparisons','active_count'),
                         ('Memberships within tolerance','membership_within_tolerance_count'),
                         ('Memberships outside tolerance','membership_outside_tolerance_count'),
                         ('RGB samples entirely within tolerance','samples_all_within_tolerance_count'),
                         ('RGB samples outside tolerance','samples_outside_tolerance_count'),
                         ('Identical winning sets (count)','winner_set_agreement_count'),
                         ('Winning-set overlap (count)','winner_overlap_agreement_count')]:
        lines.append(f'| {label} | {b[field]:,} |')
    for label, field in [('Membership agreement','membership_within_tolerance_fraction'),
                         ('Complete RGB agreement','samples_all_within_tolerance_fraction'),
                         ('Winning-set agreement','winner_set_agreement'),
                         ('Winning-set overlap agreement','winner_overlap_agreement')]:
        lines.append(f'| {label} | {pct(b[field])} |')
    lines += ['', '## Per-category statistics', '',
              '| Category | MAE | RMSE | Maximum error | Active MAE | Agreement | Outside tolerance |',
              '|---|---:|---:|---:|---:|---:|---:|']
    lookup = {r['category']:r for r in details}
    for c in categories:
        y = lookup[c]
        lines.append(f'| {c} | {fmt(y["mae"])} | {fmt(y["rmse"])} | {fmt(y["max_error"])} | '
                     f'{fmt(y["active_mae"])} | {pct(y["within_tolerance_fraction"])} | {y["outside_tolerance_count"]:,} |')
    w = b['worst']
    lines += ['', '## Worst observed case', '',
              '| Sample index (zero-based) | RGB | Category | Java | PyFCS | Absolute error |',
              '|---:|---|---|---:|---:|---:|',
              f'| {w["sample_index"]:,} | {tuple(w["rgb"])} | {w["category"]} | '
              f'{w["java"]:.17g} | {w["pyfcs"]:.17g} | {w["absolute_error"]:.17g} |',
              '', '## Interpretation and limitations', '']
    if b['membership_outside_tolerance_count'] == 0:
        lines += ['All evaluated bounded-sum memberships agree with the Java reference within the specified tolerance.', '']
    else:
        lines += [f'{b["membership_outside_tolerance_count"]:,} membership comparisons exceed the specified tolerance.', '']
    if b['max_error'] <= 1e-12:
        lines += ['The observed discrepancies are consistent with double-precision rounding. '
                  'The exact operation responsible cannot be determined from aggregated reports alone.', '']
    lines += ['These results concern aggregated memberships for the evaluated model and samples, not all possible '
              'RGB values, individual granule memberships, or exact equality of all geometric volumes.', '',
              'The Java aggregation is not explicitly identified in the available evaluation metadata. '
              'Only bounded-sum equivalence is reported here.', '',
              '## Metric definitions', '',
              '- MAE = mean absolute membership difference; RMSE = root mean squared difference.',
              '- Bias = mean(PyFCS - Java). Active comparisons have Java > 0 or PyFCS > 0; active MAE is weighted by active counts.',
              '- Membership agreement means absolute error <= tolerance. Complete RGB agreement requires every category to agree.',
              '- Winning sets include positive memberships within tolerance of the largest membership; all-zero vectors have empty sets. '
              'Overlap counts at least one shared winner or two empty sets.',
              '- All global category averages use equal sample counts. Counts are recovered from fractions and verified against per-category totals.',
              '- No raw error distribution, percentiles, unique RGB count or per-granule data can be recovered from these aggregate files.', '',
              '## Provenance', '',
              f'- JSON input SHA-256: `{provenance["report_sha256"]}`',
              f'- CSV input SHA-256: `{provenance["categories_sha256"]}`',
              '- Bounded-sum JSON and CSV per-category statistics checked for exact numeric agreement.',
              '- Processing time is the recorded evaluation-loop time, not a controlled benchmark or a standalone bounded-sum timing.', '']
    return '\n'.join(lines)


def make_plots(out, categories, summaries, details, tolerance):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    b = summaries['bounded_sum']
    lookup = {r['category']: r for r in details}
    def save(fig, stem):
        fig.tight_layout()
        for suffix in ('png', 'svg'):
            fig.savefig(out/f'{stem}.{suffix}', dpi=220, bbox_inches='tight')
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.2))
    measures = [('Memberships','membership_within_tolerance_fraction'),
                ('Complete RGB vectors','samples_all_within_tolerance_fraction'),
                ('Identical winning sets','winner_set_agreement'),
                ('Winning-set overlap','winner_overlap_agreement')]
    values = [100*b[field] for _,field in measures]
    bars = ax.barh([s for s,_ in measures], values)
    ax.bar_label(bars, labels=[f'{v:.6f}%' for v in values], padding=4, fontsize=9)
    ax.invert_yaxis(); ax.set_xlim(0,115); ax.set_xlabel('Agreement (%)')
    ax.set_title('PyFCS vs. Java — bounded-sum agreement'); ax.grid(axis='x',alpha=.2)
    save(fig,'01_agreement')

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    fields = ['mae','rmse','max_error','active_mae']; labs = ['MAE','RMSE','Maximum error','Active MAE']
    values = [b[f] for f in fields]
    valid = [(j,v) for j,v in enumerate(values) if v is not None and v>0]
    if valid:
        ax.scatter([j for j,v in valid],[v for j,v in valid],s=55)
        for j,v in valid:
            ax.annotate(f'{v:.2e}', (j,v), xytext=(0,8), textcoords='offset points', ha='center',fontsize=9)
    for j,v in enumerate(values):
        if v == 0: ax.annotate('0', (j,.025),xycoords=('data','axes fraction'),ha='center',fontsize=8)
    ax.axhline(tolerance,linestyle='--',label=f'Absolute tolerance ({tolerance:g})')
    ax.set_yscale('log'); ax.set_xticks(range(len(labs)),labs); ax.set_ylabel('Absolute membership error (log scale)')
    ax.set_title('Bounded-sum numerical errors'); ax.grid(axis='y',which='both',alpha=.2); ax.legend()
    save(fig,'02_global_errors')

    fig, ax = plt.subplots(figsize=(9, 6))
    for key,label in [('mae','MAE'),('rmse','RMSE'),('max_error','Maximum absolute error')]:
        valid = [(i,lookup[c][key]) for i,c in enumerate(categories) if lookup[c][key]>0]
        if valid: ax.scatter([v for _,v in valid],[i for i,_ in valid],s=38,label=label)
    ax.axvline(tolerance,linestyle='--',label=f'Tolerance ({tolerance:g})')
    ax.set_xscale('log'); ax.set_yticks(range(len(categories)),categories); ax.invert_yaxis()
    ax.set_xlabel('Membership error (log scale)'); ax.set_title('Bounded-sum errors by category')
    ax.grid(axis='x',which='both',alpha=.2); ax.legend(loc='lower center',bbox_to_anchor=(.5,-.22),ncol=2)
    save(fig,'03_category_errors')

    # A discrepancy plot is informative only when at least one error exceeds tolerance.
    if b['membership_outside_tolerance_count']:
        fig, ax = plt.subplots(figsize=(8.5, 5.8))
        cats = sorted(categories,key=lambda c:lookup[c]['outside_tolerance_count'],reverse=True)
        ax.barh(cats,[lookup[c]['outside_tolerance_count'] for c in cats])
        ax.invert_yaxis(); ax.set_xlabel('Membership comparisons outside tolerance')
        ax.set_title('Bounded-sum discrepancies by category'); ax.grid(axis='x',alpha=.2)
        ax.ticklabel_format(axis='x',style='plain'); save(fig,'04_discrepancies')


def default_pair():
    pairs = [(REPORTS/'comparison_full.json',REPORTS/'categories_full.csv'),
             (REPORTS/'comparison_full_old.json',REPORTS/'categories_full_old.csv')]
    available = [p for p in pairs if all(f.is_file() for f in p)]
    if not available:
        raise ValueError(f'No complete report pair in {REPORTS}; use --report and --categories.')
    if len(available)==2 and any(a.read_bytes()!=b.read_bytes() for a,b in zip(*available)):
        raise ValueError('Both original and _old report pairs exist but differ; select explicitly with --report and --categories.')
    return available[0]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,help='comparison JSON')
    p.add_argument('--categories',type=Path,help='matching category CSV')
    p.add_argument('--output-dir',type=Path,help='output directory (default: statistics_bounded_sum beside selected report)')
    p.add_argument('--no-plots',action='store_true')
    args=p.parse_args()
    try:
        if bool(args.report)!=bool(args.categories):
            raise ValueError('Supply both --report and --categories or neither.')
        j,c=(args.report,args.categories) if args.report else default_pair()
        report,cats,summary,details=load_pair(j,c)
        out=args.output_dir or j.resolve().parent/'statistics_bounded_sum'
        if not args.no_plots:
            try:
                import matplotlib  # noqa: F401
            except ImportError as e:
                raise ValueError('Install matplotlib or use --no-plots.') from e
        out.mkdir(parents=True,exist_ok=True)
        provenance=dict(report_sha256=hashlib.sha256(j.read_bytes()).hexdigest(),
                        categories_sha256=hashlib.sha256(c.read_bytes()).hexdigest())
        metadata={key:value for key,value in report.items() if key!='modes'}
        metadata['model']=name(metadata['model']); metadata['evaluation']=name(metadata['evaluation'])
        (out/'statistics_summary.json').write_text(json.dumps(dict(metadata=metadata,provenance=provenance,
                 modes=summary),indent=2,allow_nan=False)+'\n',encoding='utf-8')
        write_csv(out/'global_statistics.csv',[dict(operator=m,**{k:v for k,v in summary[m].items() if k!='worst'}) for m in MODES])
        write_csv(out/'category_statistics.csv',details)
        write_csv(out/'worst_cases.csv',[dict(operator=m,**summary[m]['worst']) for m in MODES])
        (out/'summary_EN.md').write_text(make_report(report,cats,summary,details,provenance)+'\n',encoding='utf-8')
        if not args.no_plots: make_plots(out,cats,summary,details,report['tolerance'])
        print(f'Validated {len(details)} category rows; {report["processed_samples"]:,} RGB samples.')
        for m in MODES:
            s=summary[m]; print(f'{LABELS[m]}: MAE={s["mae"]:.8g}, RMSE={s["rmse"]:.8g}, '
                f'max={s["max_error"]:.8g}, agreement={pct(s["membership_within_tolerance_fraction"])}; '
                f'outside tolerance={s["membership_outside_tolerance_count"]:,}')
        print('Statistics saved to:',out.resolve())
    except (OSError,ValueError,KeyError,TypeError) as e:
        p.exit(2,f'Error: {e}\n')


if __name__=='__main__':
    main()
