# Installation guide configuring GCP for the platform

This guide will give some hints and tips for configuring the VM's that will
run the CI setup.

This guide will give instructions for configuring and setting up the project on Google Cloud Platform (GCP) before the installation of the platform.

Currently the platform uses Linux and Windows VM instances for running regression tests.

## Setting up a Google Cloud Account
Apart from the central platform server, the platform utilises Infrastructure as a Service (IaaS) through Google Cloud Platform.

For this create a GCP account or login to an existing account [here](https://console.cloud.google.com/). 

## Creating a Google Cloud Project
The next step is to create a Google Cloud Project that the platform would use to manage instances for running regression tests and maintain a GCS bucket for samples, variables, and tester. Etc. 

For creating and managing projects, refer to the official documentation [here](https://cloud.google.com/resource-manager/docs/creating-managing-projects).

Now create a project, with project name and project id of your choice.

## Creating a Google Cloud Storage bucket

Working on Google Cloud Platform is not free, therefore it is recommended to either get a [free 90-day trial](https://console.cloud.google.com/freetrial) or [enable billing](https://console.cloud.google.com/billing) for the GCP account to get access the full set of services and increased usage limits.

Now create a GCS bucket (preferably multi-regional), refer to the official documentation [here](https://cloud.google.com/storage/docs/creating-buckets).

## Creating a Service Account

Now, create a service account with sufficient permissions that would be used by the platform, VM instances to mount and read-write the bucket contents and also manage VM instances.

If you are not the owner of the GCP project you are working on, make sure you have sufficient permissions for creating and managing service accounts; if not, request the project owner for the same.

- Create a service account [here](https://cloud.google.com/storage/docs/creating-buckets)
- Choose the service account name as per your choice, but at least provide the role of "Google Batch Service Agent" to the account. 

You might also want to understand roles in GCP, you can find the official documentation [here](https://cloud.google.com/iam/docs/understanding-roles).

Now navigate to the "keys" section of the service account created, and create a new key and download the JSON file.

Note: This is a secret key and access to the key would give access to your GCP project.

## Provide access of GCS bucket to the service account

Note: If you have provided "editor" role to the service account (not recommended), skip this step.

If you are not the owner of the GCP project you are working on, make sure you have "Service Account Admin" role; if not, request the project owner for the same.

- Go to [cloud storage page](https://console.cloud.google.com/storage/browser), and select the bucket to be used for the platform.
- Now go to "Permissions" tab and check that the service account you created has "Storage Legacy Bucket Owner" and "Storage Legacy Object Owner" permissions, if not add these permissions.

## Mounting of the Cloud Storage Bucket

To reduce the required size of the VM's, a network mount will be used to make the data accessible towards the VM's. 

This network mount is done using:
- [Google Cloud Storage FUSE](https://cloud.google.com/storage/docs/gcs-fuse) for linux VM instances.
- [Rclone](https://rclone.org/) and [WinFsp](https://winfsp.dev/) for windows VM instances.

These tools are downloaded and installed automatically using startup scripts on the VM instances.