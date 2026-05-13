#!/usr/bin/env bash
# docx_to_md.sh — Batch convert .docx files to markdown_strict via pandoc
# Usage: ./docx_to_md.sh <input_dir> <output_dir>

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <input_dir> <output_dir>" >&2
    exit 1
fi

INPUT_DIR="$1"
OUTPUT_DIR="$2"

if [[ ! -d "$INPUT_DIR" ]]; then
    echo "Error: input directory '$INPUT_DIR' does not exist." >&2
    exit 1
fi

if ! command -v pandoc &>/dev/null; then
    echo "Error: pandoc is not installed or not in PATH." >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

converted=0
skipped=0

while IFS= read -r -d '' file; do
    filename="$(basename "$file" .docx)"
    outfile="$OUTPUT_DIR/${filename}.md"

    echo "Converting: $file -> $outfile"
    if pandoc "$file" -f docx -t markdown_strict -o "$outfile"; then
        ((converted++))
    else
        echo "  Warning: failed to convert '$file'" >&2
        ((skipped++))
    fi
done < <(find "$INPUT_DIR" -maxdepth 1 -iname "*.docx" -print0)

echo ""
echo "Done. Converted: $converted, Failed: $skipped"
