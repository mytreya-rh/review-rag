#!/usr/bin/env python3
"""
Deduplicate guidelines by removing exact and high-similarity duplicates.

This script should be run between distill_guidelines.py and clustered_distill_guidelines.py
to handle potential cross-batch duplicates.

Usage:
  python src/deduplicate_guidelines.py [options]
  
Options:
  --input FILE          Input guidelines file (default: data/guidelines.json)
  --output FILE         Output deduplicated file (default: data/guidelines_deduped.json)
  --threshold FLOAT     Similarity threshold for duplicates (default: 0.85)
  --dry-run            Show what would be removed without modifying files
"""

import json
import argparse
from difflib import SequenceMatcher
from datetime import datetime


def log(msg):
    print(f"[{datetime.now()}] {msg}")


def similarity_ratio(text1, text2):
    """Calculate similarity ratio between two texts (0-1)."""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def find_duplicates(guidelines, threshold=0.85):
    """
    Find duplicate guidelines above similarity threshold.
    Returns list of indices to remove (keeps first occurrence).
    """
    to_remove = set()
    n = len(guidelines)
    
    for i in range(n):
        if i in to_remove:
            continue
            
        for j in range(i + 1, n):
            if j in to_remove:
                continue
            
            # Check exact duplicate first
            g1_text = guidelines[i].get('guideline', '')
            g2_text = guidelines[j].get('guideline', '')
            
            if not g1_text or not g2_text:
                continue
            
            # Exact match
            if g1_text == g2_text:
                log(f"  Found exact duplicate: #{i} == #{j}")
                to_remove.add(j)
                continue
            
            # Similarity check
            sim = similarity_ratio(g1_text, g2_text)
            if sim >= threshold:
                log(f"  Found similar pair ({sim:.1%}): #{i} ≈ #{j}")
                # Keep the one with more detailed rationale
                len_i = len(guidelines[i].get('rationale', ''))
                len_j = len(guidelines[j].get('rationale', ''))
                if len_j > len_i:
                    to_remove.add(i)
                    break  # i is marked for removal, move to next i
                else:
                    to_remove.add(j)
    
    return sorted(to_remove, reverse=True)


def deduplicate(input_file, output_file, threshold=0.85, dry_run=False):
    """Deduplicate guidelines from input file and save to output file."""
    
    log(f"Loading guidelines from {input_file}...")
    with open(input_file, 'r') as f:
        guidelines = json.load(f)
    
    original_count = len(guidelines)
    log(f"Loaded {original_count} guidelines")
    
    log(f"Finding duplicates (threshold: {threshold})...")
    to_remove = find_duplicates(guidelines, threshold)
    
    if not to_remove:
        log("✓ No duplicates found!")
        if not dry_run and input_file != output_file:
            # Still write output file for consistency
            with open(output_file, 'w') as f:
                json.dump(guidelines, f, indent=2)
            log(f"Wrote {original_count} guidelines to {output_file}")
        return original_count, 0
    
    log(f"Found {len(to_remove)} duplicates to remove")
    
    if dry_run:
        log("\n[DRY RUN] Would remove the following guidelines:")
        for idx in reversed(to_remove):
            g = guidelines[idx]
            log(f"  #{idx}: {g.get('concern')} - {g.get('guideline', '')[:80]}...")
        log(f"\n[DRY RUN] Would keep {original_count - len(to_remove)} guidelines")
        return original_count, len(to_remove)
    
    # Remove duplicates (in reverse order to maintain indices)
    for idx in to_remove:
        del guidelines[idx]
    
    final_count = len(guidelines)
    
    # Save deduplicated guidelines
    with open(output_file, 'w') as f:
        json.dump(guidelines, f, indent=2)
    
    log(f"✓ Saved {final_count} deduplicated guidelines to {output_file}")
    log(f"  Removed: {len(to_remove)} duplicates")
    log(f"  Reduction: {len(to_remove)/original_count*100:.1f}%")
    
    return original_count, len(to_remove)


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate guidelines by removing similar entries"
    )
    parser.add_argument(
        "--input",
        default="data/guidelines.json",
        help="Input guidelines file",
    )
    parser.add_argument(
        "--output",
        default="data/guidelines_deduped.json",
        help="Output deduplicated file",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Similarity threshold for duplicates (0-1, default: 0.85)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without modifying files",
    )
    
    args = parser.parse_args()
    
    try:
        original, removed = deduplicate(
            args.input,
            args.output,
            args.threshold,
            args.dry_run
        )
        
        if not args.dry_run and removed > 0:
            print(f"\n✓ Deduplication complete: {original} → {original - removed} guidelines")
        elif args.dry_run:
            print(f"\n[DRY RUN] Would reduce: {original} → {original - removed} guidelines")
        else:
            print(f"\n✓ No duplicates found")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

