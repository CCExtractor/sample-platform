#!/bin/bash 

curl -L -O https://github.com/GoogleCloudPlatform/gcsfuse/releases/download/v0.39.2/gcsfuse_0.39.2_amd64.deb
dpkg --install gcsfuse_0.39.2_amd64.deb
rm gcsfuse_0.39.2_amd64.deb

apt install gnupg ca-certificates
apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 3FA7E0328081BFF6A14DA29AA6A19B38D3D831EF
echo "deb https://download.mono-project.com/repo/ubuntu stable-focal main" | sudo tee /etc/apt/sources.list.d/mono-official-stable.list
sudo apt update
apt install mono-complete -y

mkdir repository
cd repository

# Use gcsfuse and import required files
mkdir temp TestFiles TestResults
gcsfuse --only-dir=TestData/ci-linux/ spdev temp
cp temp/* ./
umount temp
rmdir temp

vm_name=$(curl http://metadata.google.internal/computeMetadata/v1/instance/hostname -H "Metadata-Flavor: Google")
vm_name=(${vm_name//./ })
mkdir vm_data
# sudo gcsfuse --only-dir vm_data/${vm_name} sample-platform vm_data
sudo gcsfuse --implicit-dirs --only-dir vm_data/${vm_name} spdev vm_data

sudo gcsfuse --implicit-dirs --only-dir TestFiles spdev TestFiles
sudo gcsfuse --implicit-dirs --only-dir TestResults spdev TestResults

chmod +x bootstrap
./bootstrap
