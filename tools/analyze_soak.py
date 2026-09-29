"""唯讀分析長測紀錄；報告寫回專案的執行狀態目錄。"""
from pathlib import Path
import argparse
import hashlib
import json
import statistics
import time

ROOT = Path(__file__).resolve().parents[1]

def analyze(partial=False):
    manifest = json.loads((ROOT/'runtime/state/soak-manifest.json').read_text())
    records = []
    for file in (ROOT/'runtime/logs').glob('metrics.jsonl*'):
        for line in file.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row['time'] >= manifest['started_at']:
                records.append(row)
    records.sort(key=lambda r:r['time'])
    if not records:
        raise RuntimeError('尚無長測紀錄')
    buckets=[]
    for index in range(int(records[-1]['elapsed']//300)+1):
        group=[r['memory_mb'] for r in records if index*300 <= r['elapsed'] < (index+1)*300]
        if group:
            buckets.append({'minute_start':index*5,'samples':len(group),'median_mb':round(statistics.median(group),2),'min_mb':round(min(group),2),'max_mb':round(max(group),2)})
    warm=[r for r in records if r['elapsed']>=300]
    slope=None
    growth=None
    if len(warm)>=2:
        slope=statistics.linear_regression([r['elapsed']/60 for r in warm],[r['memory_mb'] for r in warm]).slope
        start=[r['memory_mb'] for r in warm if r['elapsed'] <600]
        end=[r['memory_mb'] for r in warm if r['elapsed'] >= records[-1]['elapsed']-300]
        growth=statistics.median(end)-statistics.median(start)
    unchanged=all((ROOT/path).exists() and hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest for path,digest in manifest['source_sha256'].items())
    final = None if partial else json.loads((ROOT/'runtime/state/final-status.json').read_text(encoding='utf-8'))
    browsers=[r['browser'] for r in records if r.get('browser') and 'probe' in r['browser']]
    latest=browsers[-1] if browsers else {}
    suspicious=slope is not None and slope>10 and growth>150
    complete=bool(final and final['uptime_seconds']>=1800 and records[-1]['elapsed']>=1795)
    live_samples=[row["live"] for row in records if row.get("live",{}).get("sequence",0)>0]
    latest_live=live_samples[-1] if live_samples else {}
    screenshot_after={str(p.relative_to(ROOT)):p.stat().st_size for p in (ROOT/"runtime/screenshots").rglob("*") if p.is_file()}
    baseline=manifest.get("screenshots_before",{})
    screenshot_unchanged=screenshot_after==baseline
    mature_live=[row["live"]["actual_fps"] for row in records if row["elapsed"]>30 and row.get("live",{}).get("target_fps")==1]
    live_rate=statistics.median(mature_live) if mature_live else 0
    checks={
        'duration_30_minutes':complete,
        'no_controller_errors':bool(final and not final['errors']),
        'no_failed_verifications':bool(final and final['verification_failures']==0),
        'no_foreground_violations':all(b.get('focus_violations',0)==0 for b in browsers),
        'no_windows_on_user_desktop':all(b.get('user_desktop_window_count',-1)==0 for b in browsers),
        'two_owned_pages':bool(browsers and all(b.get('owned_page_count')==2 for b in browsers)),
        'local_webgl_ok':bool(latest.get('probe',{}).get('webgl') and latest.get('probe',{}).get('glErrors')==0),
        'local_animation_progress':bool(latest.get('probe',{}).get('frames',0)>1000),
        'local_timer_progress':bool(latest.get('probe',{}).get('timers',0)>1000),
        'input_verifications':latest.get('probe_inputs',0)>=1500,
        'no_sustained_memory_growth':bool(complete and slope is not None and not suspicious),
        'tested_source_unchanged':unchanged,
        'live_view_frames':latest_live.get('sequence',0)>=1700,
        'live_view_normal_rate':live_rate>=.95,
        'no_screenshot_disk_growth':screenshot_unchanged,
        'bounded_latest_frame':0<latest_live.get('frame_bytes',0)<2000000,
        'clean_stop':bool(final and final['state']=='STOPPED' and not final['browser']['connected']),
    }
    report={'generated_at':time.time(),'partial':partial,'started_at':manifest['started_at'],'sample_count':len(records),
            'last_elapsed_seconds':records[-1]['elapsed'],'checks':checks,
            'overall':'PENDING' if partial else ('PASS' if all(checks.values()) else 'FAIL'),
            'memory':{'warmup_seconds':300,'buckets':buckets,'post_warmup_slope_mb_per_minute':round(slope,3) if slope is not None else None,
                      'median_growth_mb':round(growth,2) if growth is not None else None,
                      'warning_rule':'slope > 10 MB/min AND median_growth > 150 MB'},
            'last_browser':latest,'final':final,
            'live_view':{'last':latest_live,'median_normal_fps':live_rate,'screenshot_files_before':len(baseline),'screenshot_files_after':len(screenshot_after),'screenshots_unchanged':screenshot_unchanged},
            'scope':'本機模擬閉環、Kiomet 首頁、有畫面的隔離桌面與本機輸入／WebGL 測試；不含正式遊戲實戰'}
    name='soak-progress.json' if partial else 'soak-report.json'
    (ROOT/'runtime/state'/name).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['overall','last_elapsed_seconds','sample_count','checks','memory']},ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--partial',action='store_true')
    args=parser.parse_args()
    analyze(args.partial)
