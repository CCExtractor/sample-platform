#!/bin/bash 

curl -L -O https://github.com/GoogleCloudPlatform/gcsfuse/releases/download/v3.2.0/gcsfuse_3.2.0_amd64.deb
dpkg --install gcsfuse_3.2.0_amd64.deb
rm gcsfuse_3.2.0_amd64.deb

apt install gnupg ca-certificates
gpg --homedir /tmp --no-default-keyring --keyring /usr/share/keyrings/mono-official-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 3FA7E0328081BFF6A14DA29AA6A19B38D3D831EF
echo "deb [signed-by=/usr/share/keyrings/mono-official-archive-keyring.gpg] https://download.mono-project.com/repo/ubuntu stable-focal main" | sudo tee /etc/apt/sources.list.d/mono-official-stable.list
sudo apt update
apt install -y mono-complete libtesseract-dev libgpac-dev tesseract-ocr-eng fonts-noto-core

mkdir repository
cd repository

# Use gcsfuse and import required files
mkdir temp TestFiles TestResults vm_data reports

gcs_bucket=$(curl http://metadata/computeMetadata/v1/instance/attributes/bucket -H "Metadata-Flavor: Google")

vm_name=$(curl http://metadata.google.internal/computeMetadata/v1/instance/hostname -H "Metadata-Flavor: Google")
vm_name=(${vm_name//./ })

echo "${gcs_bucket} /repository/temp       gcsfuse rw,noatime,async,_netdev,noexec,user,implicit_dirs,allow_other,only_dir=TestData/ci-linux  0 0" | sudo tee -a /etc/fstab
echo "${gcs_bucket}   /repository/vm_data         gcsfuse rw,noatime,async,_netdev,noexec,user,implicit_dirs,allow_other,only_dir=vm_data/${vm_name}  0 0" | sudo tee -a /etc/fstab
echo "${gcs_bucket}   /repository/TestFiles     gcsfuse rw,noatime,async,_netdev,noexec,user,implicit_dirs,allow_other,only_dir=TestFiles,cache_dir=/tmp,file_cache_max_size_mb=3000,file_cache_cache_file_for_range_read=true,metadata_cache_ttl_secs=-1  0 0" | sudo tee -a /etc/fstab
echo "${gcs_bucket}   /repository/TestResults     gcsfuse rw,noatime,async,_netdev,noexec,user,implicit_dirs,allow_other,only_dir=TestResults  0 0" | sudo tee -a /etc/fstab

mount temp
mount vm_data
mount TestFiles
mount TestResults

cp temp/* ./

chmod +x bootstrap
./bootstrap
