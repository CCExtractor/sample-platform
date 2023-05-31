#!/bin/bash 

curl -L -O https://github.com/GoogleCloudPlatform/gcsfuse/releases/download/v0.39.2/gcsfuse_0.39.2_amd64.deb
dpkg --install gcsfuse_0.39.2_amd64.deb
rm gcsfuse_0.39.2_amd64.deb

apt install gnupg ca-certificates
apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 3FA7E0328081BFF6A14DA29AA6A19B38D3D831EF
echo "deb https://download.mono-project.com/repo/ubuntu stable-focal main" | sudo tee /etc/apt/sources.list.d/mono-official-stable.list
sudo apt update
apt install -y mono-complete libtesseract-dev libgpac-dev

mkdir repository
cd repository

# Use gcsfuse and import required files
mkdir temp TestFiles TestResults vm_data reports

gcs_bucket=$(curl http://metadata/computeMetadata/v1/instance/attributes/bucket -H "Metadata-Flavor: Google")

vm_name=$(curl http://metadata.google.internal/computeMetadata/v1/instance/hostname -H "Metadata-Flavor: Google")
vm_name=(${vm_name//./ })

echo "${gcs_bucket} /repository/temp       gcsfuse rw,noatime,async,_netdev,noexec,user,implicit_dirs,allow_other,only_dir=TestData/ci-linux  0 0" | sudo tee -a /etc/fstab
echo "${gcs_bucket}   /repository/vm_data         gcsfuse rw,noatime,async,_netdev,noexec,user,implicit_dirs,allow_other,only_dir=vm_data/${vm_name}  0 0" | sudo tee -a /etc/fstab
echo "${gcs_bucket}   /repository/TestFiles     gcsfuse rw,noatime,async,_netdev,noexec,user,implicit_dirs,allow_other,only_dir=TestFiles  0 0" | sudo tee -a /etc/fstab
echo "${gcs_bucket}   /repository/TestResults     gcsfuse rw,noatime,async,_netdev,noexec,user,implicit_dirs,allow_other,only_dir=TestResults  0 0" | sudo tee -a /etc/fstab

mount temp
mount vm_data
mount TestFiles
mount TestResults

cp temp/* ./

chmod +x bootstrap
./bootstrap
