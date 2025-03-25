#!/bin/bash

# Colors and formatting
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print section headers
print_header() {
    echo -e "\n${BOLD}${BLUE}=== $1 ===${NC}\n"
}

# Function to print success messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error messages
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to print warning/info messages
print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

protect_existing_clusters() {
    local LOCATION=$1
    local PROJECT_ID=$2

    print_header "Protecting Existing Clusters"

    FUNCTION_NAME=$(terraform -chdir=terraform output -raw discover_existing_function_name)

    URL=https://${LOCATION}-${PROJECT_ID}.cloudfunctions.net/${FUNCTION_NAME}

    curl -X POST $URL \
        -H "Authorization: bearer $(gcloud auth print-identity-token)" \
        -H "Content-Type: application/json" \
        -d '{}'
    return 0
}
