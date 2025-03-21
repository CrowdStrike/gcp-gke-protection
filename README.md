<p align="center">
   <img src="https://raw.githubusercontent.com/CrowdStrike/falconpy/main/docs/asset/cs-logo.png" alt="CrowdStrike logo" width="500"/>
</p>

# GKE Cluster Protection

Description of solution ...

## Architecture

Describe architecture ...

## Prerequisites

### CrowdStrike

**Provision Credentials**

API credentials with the following scopes need to be created

- scope 1
- scope 2

### GCP

**Enable APIs**

The following APIs need to be enabled.

- Cloud Functions
- Cloud Asset
- Pub Sub

Enable all APIs by visiting [this URL](example.com)

**Provision Service Account**

A service account needs to be created. The service account must have the following roles at the *Scope* you want to be protected.

- role 1
- role 2

## Deployment

### Deployment Scopes

- **Organization**: Will discover and protect clusters for all projects within a given organization
- **Folder**: Will discover and protect clusters for all projects within a given folder
- **Project**: Will discover and protect clusters for a given project

### Execution

Start the deployment process by executing the following command in the root directory of this repository

```shell
./install.sh
```

The script will ask you for a series of values:

- DEPLOYMENT_PROJECT_ID - Account solution should be deployed in
- FALCON_CLIENT_ID - Client ID for falcon api
- FALCON_CLIENT_SECRET - Client Secret for falcon api
- LOCATION - GCP location to deploy to
- SERVICE_ACCOUNT_EMAIL - Email of the service account that has required roles
- SCOPE - Chose deployment scope. Must be one of projects, folders, organizations
- SCOPE_IDENTIFIER - you will need to supply one of the following values depending on the scope selected
  - organizations: organization id
  - folders: folder id
  - projects: project id, or project name

The script will validate that the required APIs have been enabled and then deploy the terraform template to build out the resources required fro cluster protection. If everything is successful, you should see a message at the end similar to this.

\#TODO:Add image of script result.

#### Post Execution

The install script will ask you if you want to discover and protect existing clusters. If you select yes, it will scan all projects within the scope chose to find clusters that were created prior to deploying te solution, and initiate cluster protection.

### Triggering Existing Cluster Discovery Post Deployment

If you choose not to protect existing clusters, you can trigger it by executing

```shell
...
```

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details on how to submit pull requests.

## Support

Write support disclaimer...

For additional support, please see the [SUPPORT.md](SUPPORT.md) file.

## License

This project is licensed under the [MIT License](LICENSE).
