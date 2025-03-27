#!/bin/bash
set -e # Exit on any error

source utils.sh

# Function to validate prerequisites
validate_prerequisites() {
    print_header "Validating Prerequisites"

    print_info "Checking if Cloud Functions API is enabled..."
    check_api_enabled $1 "cloudfunctions.googleapis.com" || return 1

    print_info "Checking if Pub/Sub API is enabled..."
    check_api_enabled $1 "pubsub.googleapis.com" || return 1

    print_info "Checking if Cloud Asset API is enabled..."
    check_api_enabled $1 "cloudasset.googleapis.com" || return 1

    return 0
}

check_api_enabled() {
    local project_id="$1"
    local api_name="$2"

    if [ -z "$project_id" ] || [ -z "$api_name" ]; then
        print_error "Usage: check_api_enabled PROJECT_ID API_NAME"
        return 1
    fi

    if gcloud services list --project="${project_id}" \
        --filter="config.name:${api_name}" \
        --format="get(config.name)" | grep -q "^${api_name}$"; then
        print_success "API ${api_name} is enabled"
        return 0
    else
        print_error "API ${api_name} is not enabled"
        return 1
    fi
}

# Function to deploy terraform
deploy_terraform() {
    print_header "Deploying Terraform Template"
    terraform -chdir=terraform init
    terraform -chdir=terraform apply \
        --var "falcon_client_id=${1}" \
        --var "falcon_client_secret=${2}" \
        --var "location=${3}" \
        --var "service_account_email=${4}" \
        --var "scope=${5}" \
        --var "scope_identifier=${6}" \
        --var "deployment_project_id=${7}" \
        --auto-approve
    if [ $? -ne 0 ]; then
        return 1
    fi

    print_success "\nSolution deployment completed successfully!"

    return 0
}

# Function to protect existing clusters
protect_existing_clusters() {
    local LOCATION=$1
    local PROJECT_ID=$2

    print_header "Protecting Existing Clusters"
    print_info "Using scope: $SCOPE/$SCOPE_IDENTIFIER"

    FUNCTION_NAME=$(terraform -chdir=terraform output -raw discover_existing_function_name)

    URL=https://${LOCATION}-${PROJECT_ID}.cloudfunctions.net/${FUNCTION_NAME}

    curl -X POST $URL \
        -H "Authorization: bearer $(gcloud auth print-identity-token)" \
        -H "Content-Type: application/json" \
        -d '{}'
    return 0
}

# Main script
main() {
    print_header "CrowdStrike Kubernetes Protection Deployment"

    print_info "Please provide the id of the project you will be deploying the solution to:"
    echo -en "${BOLD}DEPLOYMENT_PROJECT_ID${NC}: "
    read DEPLOYMENT_PROJECT_ID
    if [ -z "$DEPLOYMENT_PROJECT_ID" ]; then
        print_error "DEPLOYMENT_PROJECT_ID is required"
        exit 1
    fi

    # Validate prerequisites
    if ! validate_prerequisites $DEPLOYMENT_PROJECT_ID; then
        print_error "Prerequisites validation failed. Exiting..."
        exit 1
    fi

    # Collect required variables
    print_header "Falcon Credentials"
    print_info "Please provide the following details:"

    echo -en "${BOLD}FALCON_CLIENT_ID${NC}: "
    read FALCON_CLIENT_ID
    if [ -z "$FALCON_CLIENT_ID" ]; then
        print_error "FALCON_CLIENT_ID is required"
        exit 1
    fi

    echo -en "${BOLD}FALCON_CLIENT_SECRET${NC}: "
    read -s FALCON_CLIENT_SECRET
    echo
    if [ -z "$FALCON_CLIENT_SECRET" ]; then
        print_error "FALCON_CLIENT_SECRET is required"
        exit 1
    fi

    print_header "Deployment details"
    print_info "Please provide the following details:"

    echo -en "${BOLD}LOCATION${NC} [us-central1]: "
    read LOCATION
    LOCATION=${LOCATION:-"us-central1"}
    echo
    if [ -z "$LOCATION" ]; then
        print_error "LOCATION is required"
        exit 1
    fi

    echo -en "${BOLD}SERVICE_ACCOUNT_EMAIL${NC}: "
    read SERVICE_ACCOUNT_EMAIL
    echo
    if [ -z "$SERVICE_ACCOUNT_EMAIL" ]; then
        print_error "SERVICE_ACCOUNT_EMAIL is required"
        exit 1
    fi

    echo -en "${BOLD}SCOPE (projects/folders/organizations)${NC}: "
    read SCOPE
    echo
    if [ -z "$SCOPE" ]; then
        print_error "SCOPE is required"
        exit 1
    fi

    echo -en "${BOLD}SCOPE_IDENTIFIER${NC}: "
    read SCOPE_IDENTIFIER
    echo
    if [ -z "$SCOPE_IDENTIFIER" ]; then
        print_error "SCOPE_IDENTIFIER is required"
        exit 1
    fi

    # Deploy terraform
    if ! deploy_terraform "$FALCON_CLIENT_ID" "$FALCON_CLIENT_SECRET" "$LOCATION" "$SERVICE_ACCOUNT_EMAIL" "$SCOPE" "$SCOPE_IDENTIFIER" "$DEPLOYMENT_PROJECT_ID"; then
        print_error "Terraform deployment failed. Exiting..."
        exit 1
    fi

    # Ask about protecting existing clusters
    echo -en "\n${BOLD}Do you want to discover and protect existing clusters? (yes/no)${NC}: "
    read PROTECT_CLUSTERS
    PROTECT_CLUSTERS=$(echo "$PROTECT_CLUSTERS" | tr '[:upper:]' '[:lower:]')

    if [ "$PROTECT_CLUSTERS" = "yes" ]; then
        if ! protect_existing_clusters "$LOCATION" "$DEPLOYMENT_PROJECT_ID"; then
            print_error "Cluster protection failed. Exiting..."
            exit 1
        fi
    else
        print_info "To protect existing clusters at a later time, you can execute './protect_existing.sh $LOCATION $DEPLOYMENT_PROJECT_ID'"
    fi

    print_success "\nDeployment completed successfully!"
}

# Handle script interruption
trap 'echo -e "\n${RED}Operation cancelled by user${NC}"; exit 1' INT

# Execute main function
main
