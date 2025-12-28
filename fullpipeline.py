# batch_pipeline.py
import logging
import pandas as pd
from pathlib import Path
from fullpipeline import run_stage, download_media, url2srt, vtt2txt, transcript2csv, cut_clips, extract_embeddings
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--excel", required=True, help="Path to Excel file with URLs")
    p.add_argument("--url-column", default="url", help="Column name containing URLs")
    p.add_argument("--workdir", default="batch_runs", help="Parent directory for all runs")
    p.add_argument("--limit", type=int, help="Limit clips per video")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--workers", type=int, default=1, help="Parallel workers (use 1 to start)")
    p.add_argument("--skip-existing", action="store_true", help="Skip already processed URLs")
    
    p.add_argument("--workers", type=int, default=1, help="Parallel workers (use 1 to start)")

    return p.parse_args()

def process_single_url(url, workdir, limit=None, dry_run=False):
    """
    Process a single URL through the entire pipeline.
    Returns (url, success, error_message)
    """
    try:
        logging.info(f"🚀 Starting pipeline for: {url}")
        
        media = run_stage("Download media", download_media, url, workdir / "media.mp4")
        srt = run_stage("Download transcript", url2srt, url, workdir / "captions.srt")
        txt = run_stage("SRT → TXT", vtt2txt, srt, workdir / "transcript.txt")
        csv = run_stage("Transcript → CSV", transcript2csv, txt, workdir / "segments.csv")
        clips_dir = run_stage("Cut clips", cut_clips, media, csv, workdir / "clips", limit, dry_run)
        embeddings_dir = run_stage("Extract embeddings", extract_embeddings, clips_dir, workdir / "embeddings")
        
        logging.info(f"✅ Successfully processed: {url}")
        return (url, True, None)
    
    except Exception as e:
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        logging.error(f"❌ Failed to process {url}: {error_msg}")
        return (url, False, error_msg)

def sanitize_dirname(url):
    """Convert URL to safe directory name"""
    # Remove protocol and replace special chars
    name = url.replace("https://", "").replace("http://", "")
    name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in name)
    return name[:100]  # Limit length

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    args = parse_args()
    
    # Read Excel file
    try:
        df = pd.read_excel(args.excel)
    except Exception as e:
        logging.error(f"Failed to read Excel file: {e}")
        return
    
    if args.url_column not in df.columns:
        logging.error(f"Column '{args.url_column}' not found. Available: {list(df.columns)}")
        return
    
    urls = df[args.url_column].dropna().tolist()
    logging.info(f"📊 Found {len(urls)} URLs to process")
    
    # Create parent workdir
    parent_workdir = Path(args.workdir)
    parent_workdir.mkdir(exist_ok=True)
    
    results = []
    
    if args.workers == 1:
        # Sequential processing (easier to debug)
        for idx, url in enumerate(urls, 1):
            logging.info(f"\n{'='*80}")
            logging.info(f"Processing {idx}/{len(urls)}: {url}")
            logging.info(f"{'='*80}")
            
            # Create unique workdir for this URL
            url_dirname = f"{idx:03d}_{sanitize_dirname(url)}"
            workdir = parent_workdir / url_dirname
            
            if args.skip_existing and workdir.exists():
                logging.info(f"⏭️  Skipping existing: {url}")
                results.append((url, True, "Skipped - already exists"))
                continue
            
            workdir.mkdir(exist_ok=True)
            result = process_single_url(url, workdir, args.limit, args.dry_run)
            results.append(result)
    
    else:
        # Parallel processing 
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {}
            
            for idx, url in enumerate(urls, 1):
                url_dirname = f"{idx:03d}_{sanitize_dirname(url)}"
                workdir = parent_workdir / url_dirname
                
                if args.skip_existing and workdir.exists():
                    logging.info(f"⏭️  Skipping existing: {url}")
                    results.append((url, True, "Skipped - already exists"))
                    continue
                
                workdir.mkdir(exist_ok=True)
                future = executor.submit(process_single_url, url, workdir, 
                                         args.limit, 
                                         args.dry_run)
                futures[future] = url
            
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
    
    # Generate summary report
    logging.info("\n" + "="*80)
    logging.info("📈 BATCH PROCESSING SUMMARY")
    logging.info("="*80)
    
    successful = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]
    
    logging.info(f"✅ Successful: {len(successful)}/{len(urls)}")
    logging.info(f"❌ Failed: {len(failed)}/{len(urls)}")
    
    if failed:
        logging.info("\n❌ Failed URLs:")
        for url, _, error in failed:
            logging.info(f"  - {url}")
            logging.info(f"    Error: {error[:200]}...")
    
    # Save results to CSV
    results_df = pd.DataFrame(results, columns=['url', 'success', 'error'])
    results_path = parent_workdir / "batch_results.csv"
    results_df.to_csv(results_path, index=False)
    logging.info(f"\n📄 Results saved to: {results_path}")

if __name__ == "__main__":
    main()