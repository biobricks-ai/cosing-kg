#!/bin/sh

set -eu

# Get local path
localpath=$(pwd)
echo "Local path: $localpath"

# Set raw path
rawpath="$localpath/raw"
echo "Raw path: $rawpath"

# Create brick directory
brickpath="$localpath/brick"
mkdir -p $brickpath
echo "Brick path: $brickpath"

base_uri="https://ec.europa.eu/growth/tools-databases/cosing/"
rdf2hdt -i -p -B "$base_uri" $rawpath/cosing.nt $brickpath/cosing.hdt
