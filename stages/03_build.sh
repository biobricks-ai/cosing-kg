#!/usr/bin/env bash

# Script to process unzipped files and build parquet files

# Get local path
localpath=$(pwd)
echo "Local path: $localpath"

# Set list path
listpath="$localpath/list"
mkdir -p $listpath
echo "List path: $listpath"

# Set raw path
rawpath="$localpath/raw"
echo "Raw path: $rawpath"

# Create brick directory
brickpath="$localpath/brick"
mkdir -p $brickpath
echo "Brick path: $brickpath"

# Process raw files and create parquet files in parallel
# calling a Python function with arguments input and output filenames
cat $listpath/files.txt | tail -n +4 | xargs -P14 -n1 bash -c '
  filename="${1%.*}"
  echo '$rawpath'/$filename/$filename.txt
  echo '$brickpath'/$filename.parquet
  python stages/csv2parquet.py '$rawpath'/$filename.txt '$brickpath'/$filename.parquet
' {}