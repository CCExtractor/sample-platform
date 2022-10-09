#!/bin/bash
#
# Installer for the CCExtractor sample platform
#
# More information can be found on:
# https://github.com/CCExtractor/sample-platform
#
dir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
root_dir=$( cd "${dir}"/../ && pwd)
clear
date=$(date +%Y-%m-%d-%H-%M)
install_log="${dir}/PlatformInstall_${date}_log.txt"
echo "Welcome to the CCExtractor platform installer!"
if [[ "$EUID" -ne 0 ]]
    then
        echo "You must be a root user to install CCExtractor platform." 2>&1
        exit -1
fi
echo ""
echo "Detailed information will be written to $install_log"
echo "Please read the installation instructions carefully before installing."
echo ""
echo "-------------------------------"
echo "|   Installing dependencies   |"
echo "-------------------------------"
echo ""
echo "* Updating package list"
apt-get update >> "$install_log" 2>&1
echo "* Installing nginx, python, pip, mediainfo and gunicorn"
apt-get -q -y install nginx python3 python-is-python3 python3-pip mediainfo gunicorn3 >> "$install_log" 2>&1
rm -f /etc/nginx/sites-available/default
rm -f /etc/nginx/sites-enabled/default
for file in /etc/init.d/mysql*
do
    if [ ! -f "$file" ]; then
        mysql_user_resp="Y"
        while [ "$mysql_user_resp" != "N" ]; do
            echo "* Installing MySQL (root password will be empty!)"
            apt-get install -y mysql-server >> "$install_log" 2>&1
            if [ $? -ne 0 ]; then
                read -e -r -p "MySQL installation failed! Do you want to try again? [Y for yes | N for No | Q to quit installation] " -i "Y" mysql_user_resp
                if [ "$mysql_user_resp" = "Q" ]; then
                    exit 1
                fi
            fi
            if [  -f "$file" ]; then
                break
            fi
        done
    fi
done

RED='\033[0;31m'
NC='\033[0m' 

userInput () {
    # Utility function to take user inputs
    # $1 -> Variable Name
    # $2 -> Variable details
    # $3 -> Default Value (pass "" if none)
    # $4 -> Variable importance description (if variable is set to not required)
    # $5 -> Whether variable is required or not (pass 1 if required)
    while : ; do
    read -e -r -p "$(tput bold)$2$(tput sgr0) " -i "$3" newinput
	[[ $newinput == "" && $5 == "1" ]] || break
	echo "This is a required parameter, cannot be empty!"
    done
    printf -v $1 "$newinput"
    if [[ $newinput == "" && $4 != "" ]]; then
        echo -e "${RED}WARNING${NC}: ${2}\b not set, ${4} might not work as intended."
    fi
}

echo "* Update pip, setuptools and wheel"
python -m pip install --upgrade pip setuptools wheel >> "$install_log" 2>&1
echo "* Installing pip dependencies"
python -m pip install -r "${root_dir}/requirements.txt" >> "$install_log" 2>&1
echo ""
echo "-------------------------------"
echo "|        Configuration        |"
echo "-------------------------------"
echo ""
echo "In order to configure the platform, we need some information from you. Please reply to the following questions:"
echo ""
read -s -e -r -p  "$(tput bold)Password of the 'root' user of MySQL:$(tput sgr0) " -i "" db_root_password
echo ""
# Verify password

supress_warning=$(mysql_config_editor set --login-path=root_login --host=localhost --user=root --password "${db_root_password}") >> "$install_log" 2>&1
while ! MYSQL_PWD=$db_root_password mysql --login-path=root_login -e ";" ; do
    read -s -e -r -p "$(tput bold)Invalid password, please retry:$(tput sgr0) " -i "" db_root_password
    echo "" 
    supress_warning=$(mysql_config_editor set --login-path=root_login --host=localhost --user=root --password "${db_root_password}") >> "$install_log" 2>&1
done

userInput db_name "Database name for storing data:" "sample_platform" "" 1
MYSQL_PWD=$db_root_password mysql --login-path=root_login -e "CREATE DATABASE IF NOT EXISTS ${db_name};" >> "$install_log" 2>&1
# Check if DB exists
db_exists=$(MYSQL_PWD=$db_root_password mysql --login-path=root_login -se"USE ${db_name};" 2>&1)
if [ ! "${db_exists}" == "" ]; then
    echo "Failed to create the database! Please check the installation log!"
    exit -1
fi
userInput db_user "Username to connect to ${db_name}:" "sample_platform" "" 1
# Check if user exists
db_user_exists=$(MYSQL_PWD=$db_root_password mysql --login-path=root_login -sse "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = '${db_user}')")

if [ "${db_user_exists}" = 0 ]; then
    rand_pass=$(< /dev/urandom tr -dc 'a-zA-Z0-9' | fold -w 16 | head -n 1)
    userInput db_user_password "Password for ${db_user} (will be created):" $rand_pass ""
    # Attempt to create the user
    MYSQL_PWD=$db_root_password mysql --login-path=root_login -e "CREATE USER '${db_user}'@'localhost' IDENTIFIED BY '${db_user_password}';" >> "$install_log" 2>&1
    db_user_exists=$(MYSQL_PWD=$db_root_password mysql --login-path=root_login -sse "SELECT EXISTS(SELECT 1 FROM mysql.user WHERE user = '$db_user')")
    if [ "${db_user_exists}" = 0 ]; then
        echo "Failed to create the user! Please check the installation log!"
        exit -1
    fi
else
    read -s -e -r -p "$(tput bold)Password for ${db_user}:$(tput sgr0) " db_user_password
    supress_warning=$(mysql_config_editor set --login-path=check_login --host=localhost --user="${db_user}" --password "${db_root_password}") >> "$install_log" 2>&1
    # Check if we have access
    while ! MYSQL_PWD=$db_user_password mysql --login-path=check_login  -e ";" ; do
       read -s -e -r -p "$(tput bold)Invalid password, please retry:$(tput sgr0) " -i "" db_user_password
       supress_warning=$(mysql_config_editor set --login-path=check_login --host=localhost --user="${db_user}" --password "${db_root_password}") >> "$install_log" 2>&1
    done
fi
supress_warning=$(mysql_config_editor set --login-path=user_login --host=localhost --user="${db_user}" --password "${db_user_password}") >> "$install_log" 2>&1
# Grant user access to database
MYSQL_PWD=$db_root_password mysql --login-path=root_login -e "GRANT ALL ON ${db_name}.* TO '${db_user}'@localhost;" >> "$install_log" 2>&1
# Check if user has access
db_access=$(MYSQL_PWD=$db_root_password mysql --login-path=user_login -se "USE ${db_name};" 2>&1)
if [ ! "${db_access}" == "" ]; then
    echo "Failed to grant user access to database! Please check the installation log!"
    exit -1
fi
userInput sample_response "Do you want to install a sample database? (Enter 'y' for yes):"
# Request information for generating the config.py file
echo ""
echo "For the following questions, press enter to leave a field blank."
userInput config_server_name "(Sub)domain this will be running on?" "127.0.0.1" "" 1
userInput config_application_root "Application root (if not a whole (sub)domain, enter the path. None if whole (sub)domain):" "None" "" 1
echo "You can get details about creating a Personal-Access-Token, https://help.github.com/articles/creating-an-access-token-for-command-line-use/)"
userInput github_token "GitHub Token:" "" "Creating GitHub issues, updating comments on Pull Requests" 0
userInput github_owner_name "GitHub Owner Name:" "CCExtractor" "" 1
userInput github_repository "GitHub repository:" "ccextractor" "" 1
userInput email_domain "Email Domain:" $config_server_name "" 1
echo "You can generate your own Email API key here, https://www.mailgun.com/)"
userInput email_api_key "Email API key:" "" "Authentication, Email notification related functions" 0 
hmac_key=$(head -80 /dev/urandom | LC_ALL=c tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)
echo "You can get details about creating deployment secrets here, https://developer.github.com/webhooks/"
userInput github_deploy_key "GitHub Automated Deploy Webhook Secret:" "" "Automated deployment, mod_deploy module functions" 0 
echo "You can get details about creating WEBHOOK_SECRET here, https://developer.github.com/webhooks/"
userInput github_ci_key "GitHub CI Webhook Secret:" "" "CI related functions (mod_ci module)" 0
userInput server_name "FTP Server IP/Domain name:" $config_server_name "" 1
userInput ftp_port "FTP port:" "21" "" 1
userInput max_content_length "Max HTTP sample size (in bytes):" "536870912" "" 1
userInput min_pwd_len "Minimum password length:" "10" "" 1
userInput max_pwd_len "Maximum password length:" "500" "" 1

userInput gcp_service_account_file "GCP service account file name (to be placed at root of project):" "service-account.json" "" 1
userInput sample_platform_project_name "GCP Project Name for the platform:" "" "" 1
userInput sample_platform_project_number "GCP Project Number for the platform:" "" "" 1
userInput gcp_instance_zone_name "Zone name for GCP Instances:" "us-west4-b" "" 1
userInput gcp_instance_machine_type "Machine type for GCP Instances:" "n1-standard-1" "" 1
userInput windows_instance_project_name "Windows GCP instance project name:" "windows-cloud" "" 1
userInput windows_instance_family_name "Windows GCP instance family name:" "windows-2019" "" 1
userInput linux_instance_project_name "Linux GCP instance project name:" "ubuntu-os-cloud" "" 1
userInput linux_instance_family_name "Linux GCP instance family name: " "ubuntu-minimal-2204-lts" "" 1
userInput gcp_instance_max_runtime "GCP Instance Max Runtime (In minutes):" "120" "" 1
userInput gcs_bucket_name "Google Cloud Storage bucket name:" "" "" 1
userInput gcs_bucket_location "Google Cloud Storage bucket location:" "" "" 1
userInput gcs_bucket_location_type "Google Cloud Storage bucket location type:" "" "" 1
userInput signed_url_expiry_time "Signed Download URLs expiry time (In minutes):" "720" "" 1


echo ""
echo "In the following lines, enter the path "
userInput config_ssl_cert "    To SSL certificate:" "/etc/letsencrypt/live/${config_server_name}/fullchain.pem" "" 1
userInput config_ssl_key "    To SSL key:" "/etc/letsencrypt/live/${config_server_name}/privkey.pem" "" 1
userInput sample_repository "    To the root directory containing all files (Samples, reports etc.):" "/repository" "" 1

echo "Setting up the directories.."

{
    mkdir -p "${sample_repository}" 
    mkdir -p "${sample_repository}/ci-tests" 
    mkdir -p "${sample_repository}/unsafe-ccextractor"
    mkdir -p "${sample_repository}/TempFiles"
    mkdir -p "${sample_repository}/LogFiles"
    mkdir -p "${sample_repository}/TestResults"
    mkdir -p "${sample_repository}/TestFiles"
    mkdir -p "${sample_repository}/TestFiles/media"
    mkdir -p "${sample_repository}/QueuedFiles"
    mkdir -p "${sample_repository}/TestData/ci-linux"
    mkdir -p "${sample_repository}/TestData/ci-windows"
} >> "$install_log" 2>&1

config_db_uri="mysql+pymysql://${db_user}:${db_user_password}@localhost:3306/${db_name}"
# Request info for creating admin account
userInput admin_name "Admin username:" "admin" "We need some information for the admin account" 1
userInput admin_email "Admin email:" "" "" 1

echo "Enter Admin password (size of password >= 1)"
while [[ $admin_password == "" ]];do
   read -s -e -r -p  "Admin password: " admin_password
   echo ""
   read -s -e -r -p  "Confirm admin password: " confirm_admin_password
   echo ""
   if [[ $admin_password != $confirm_admin_password ]]; then
        echo "Entered passwords did not match! Retrying..."
        admin_password=""
   fi
done
echo "Creating admin account: "
python "${root_dir}/install/init_db.py" "${config_db_uri}" "${admin_name}" "${admin_email}" "${admin_password}"
# Create sample database if user wanted to
if [ "${sample_response}" == 'y' ]; then
    echo "Creating sample database.."
    cp -r "${dir}/sample_files/*" "${sample_repository}/TestFiles"
    python "${dir}/sample_db.py" "${config_db_uri}"
fi
echo ""
echo "-------------------------------"
echo "|      Finalizing install     |"
echo "-------------------------------"
echo ""
echo "* Generating secret keys"
# Write two secret keys (1 for session, 1 for CSRF)
head -c 24 /dev/urandom > "${dir}/../secret_key"
head -c 24 /dev/urandom > "${dir}/../secret_csrf"
# Write config file
echo "* Generating config file"
echo "# Auto-generated configuration by install.sh
APPLICATION_ROOT = ${config_application_root}
CSRF_ENABLED = True
DATABASE_URI = '${config_db_uri}?charset=utf8'
GITHUB_TOKEN = '${github_token}'
GITHUB_OWNER = '${github_owner_name}'
GITHUB_REPOSITORY = '${github_repository}'
SERVER_NAME = '${server_name}'
EMAIL_DOMAIN = '${email_domain}'
EMAIL_API_KEY = '${email_api_key}'
HMAC_KEY = '${hmac_key}'
GITHUB_DEPLOY_KEY = '${github_deploy_key}'
GITHUB_CI_KEY = '${github_ci_key}'
INSTALL_FOLDER = '${root_dir}'
SAMPLE_REPOSITORY = '${sample_repository}'
SESSION_COOKIE_PATH = '/'
FTP_PORT = $ftp_port
MAX_CONTENT_LENGTH = $max_content_length
MIN_PWD_LEN = $min_pwd_len
MAX_PWD_LEN = $max_pwd_len


# GCP SPECIFIC CONFIG
SCOPES = ['https://www.googleapis.com/auth/cloud-platform']
SERVICE_ACCOUNT_FILE = '${gcp_service_account_file}'
ZONE = '${gcp_instance_zone_name}'
PROJECT_NAME = '${sample_platform_project_name}'
MACHINE_TYPE = f'zones/{ZONE}/machineTypes/${gcp_instance_machine_type}'
WINDOWS_INSTANCE_PROJECT_NAME = '${windows_instance_project_name}'
WINDOWS_INSTANCE_FAMILY_NAME = '${windows_instance_family_name}'
LINUX_INSTANCE_PROJECT_NAME = '${linux_instance_project_name}'
LINUX_INSTANCE_FAMILY_NAME = '${linux_instance_family_name}'
GCP_INSTANCE_MAX_RUNTIME = $gcp_instance_max_runtime  # In minutes
GCS_BUCKET_NAME = '${gcs_bucket_name}'
GCS_SIGNED_URL_EXPIRY_LIMIT = $signed_url_expiry_time  # In minutes
" > "${dir}/../config.py"
# Ensure the files are executable by www-data
chown -R www-data:www-data "${root_dir}" "${sample_repository}"
echo "* Creating startup script"

{
    cp "${dir}/platform" /etc/init.d/platform
    sed -i "s#BASE_DIR#${root_dir}#g" /etc/init.d/platform
    chmod 755 /etc/init.d/platform
    update-rc.d platform defaults
}  >> "$install_log" 2>&1
echo "* Creating RClone config file"

{
    cp  "${root_dir}/install/ci-vm/ci-windows/rclone_sample.conf"  "${root_dir}/install/ci-vm/ci-windows/ci/rclone.conf"
    sed -i "s#GCS_BUCKET_NAME#${gcs_bucket_name}#g" "${root_dir}/install/ci-vm/ci-windows/ci/rclone.conf"
    sed -i "s#GCP_PROJECT_NUMBER#${sample_platform_project_number}#g" "${root_dir}/install/ci-vm/ci-windows/ci/rclone.conf"
    sed -i "s#GCS_BUCKET_LOCATION_TYPE#${gcs_bucket_location_type}#g" "${root_dir}/install/ci-vm/ci-windows/ci/rclone.conf"
    sed -i "s#GCS_BUCKET_LOCATION#${gcs_bucket_location}#g" "${root_dir}/install/ci-vm/ci-windows/ci/rclone.conf"
}  >> "$install_log" 2>&1
echo "* Creating Nginx config"

{
    cp "${dir}/nginx.conf" /etc/nginx/sites-available/platform
    sed -i "s/NGINX_HOST/${config_server_name}/g" /etc/nginx/sites-available/platform
    sed -i "s#NGINX_CERT#${config_ssl_cert}#g" /etc/nginx/sites-available/platform 
    sed -i "s#NGINX_KEY#${config_ssl_key}#g" /etc/nginx/sites-available/platform 
    sed -i "s#NGINX_DIR#${root_dir}#g" /etc/nginx/sites-available/platform 
    ln -s /etc/nginx/sites-available/platform /etc/nginx/sites-enabled/platform
} >> "$install_log" 2>&1
echo "* Moving variables and runCI files"

{
    cp $root_dir/install/ci-vm/ci-windows/ci/* "${sample_repository}/TestData/ci-windows/"
    cp $root_dir/install/ci-vm/ci-linux/ci/* "${sample_repository}/TestData/ci-linux/"
} >> "$install_log" 2>&1
echo "* Reloading nginx"
service nginx reload >> "$install_log" 2>&1
echo ""
echo "* Starting Platform..."
service platform start
echo "Platform installed!"
