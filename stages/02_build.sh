#!/usr/bin/env bash

# Script to process unzipped files and build parquet files

# Get local path
localpath=$(pwd)
echo "Local path: $localpath"

# Set download path
downloadpath="$localpath/download"
echo "Download path: $downloadpath"

# Create brick directory
brickpath="$localpath/brick"
mkdir -p $brickpath
echo "Brick path: $brickpath"

perl stages/csv-to-rdf.pl $downloadpath/*.csv $brickpath/cosing.nt
