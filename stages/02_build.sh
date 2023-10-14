#!/usr/bin/env bash

# Script to process CSV to RDF

# Get local path
localpath=$(pwd)
echo "Local path: $localpath"

# Set download path
downloadpath="$localpath/download"
echo "Download path: $downloadpath"

# Create raw directory
rawpath="$localpath/raw"
mkdir -p $rawpath
echo "Raw path: $rawpath"

perl stages/csv-to-rdf.pl $downloadpath/*.csv $rawpath/cosing.nt
