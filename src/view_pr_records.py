#!/usr/bin/env python3
"""
View pr_records.jsonl in a readable format.

Usage:
  python src/view_pr_records.py [options]
  
Options:
  --limit N         Show only first N records (default: all)
  --record N        Show only record number N (1-indexed)
  --output FILE     Save formatted output to file (default: print to stdout)
  --compact         Show compact summary instead of full records
"""

import json
import sys
import argparse


def format_record_compact(record, index):
    """Format a record in compact summary format."""
    return (
        f"\n{'='*80}\n"
        f"Record #{index}\n"
        f"{'='*80}\n"
        f"Repo: {record.get('repo', 'N/A')}\n"
        f"PR: #{record.get('pr_number', 'N/A')}\n"
        f"File: {record.get('file_path', 'N/A')}\n"
        f"Line: {record.get('line_start', 'N/A')}\n"
        f"Comment (preview): {record.get('comment_body', '')[:100]}...\n"
    )


def format_record_full(record, index):
    """Format a record in full JSON format."""
    return (
        f"\n{'='*80}\n"
        f"Record #{index}\n"
        f"{'='*80}\n"
        f"{json.dumps(record, indent=2, ensure_ascii=False)}\n"
    )


def main():
    parser = argparse.ArgumentParser(
        description="View pr_records.jsonl in a readable format"
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        default="data/pr_records.jsonl",
        help="Input JSONL file (default: data/pr_records.jsonl)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Show only first N records",
    )
    parser.add_argument(
        "--record",
        type=int,
        help="Show only record number N (1-indexed)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save formatted output to file",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Show compact summary instead of full records",
    )
    
    args = parser.parse_args()
    
    try:
        with open(args.input_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        total_records = len(lines)
        print(f"Total records: {total_records}", file=sys.stderr)
        
        output_lines = []
        
        for i, line in enumerate(lines, 1):
            # Skip if we only want a specific record
            if args.record and i != args.record:
                continue
            
            # Stop if we've reached the limit
            if args.limit and i > args.limit:
                break
            
            try:
                record = json.loads(line)
                
                if args.compact:
                    output_lines.append(format_record_compact(record, i))
                else:
                    output_lines.append(format_record_full(record, i))
                    
            except json.JSONDecodeError as e:
                print(f"Error parsing record #{i}: {e}", file=sys.stderr)
                continue
        
        # Output results
        output = "".join(output_lines)
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Output saved to: {args.output}", file=sys.stderr)
        else:
            print(output)
            
    except FileNotFoundError:
        print(f"Error: File not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()






