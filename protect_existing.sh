#!/bin/bash
set -e # Exit on any error

source utils.sh

main() {
    protect_existing_clusters $1 $2
}

main $1 $2
