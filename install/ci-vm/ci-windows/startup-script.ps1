Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
choco install winfsp -y

cd C:\Windows\Temp

curl.exe https://downloads.rclone.org/v1.59.0/rclone-v1.59.0-windows-amd64.zip --output rclone.zip
Expand-Archive -Path rclone.zip -DestinationPath .\
New-Item -Path '.\repository' -ItemType Directory
Copy-Item -Path .\rclone-v1.59.0-windows-amd64\rclone.exe -Destination .\repository\

cd repository
New-Item -Path '.\reports' -ItemType Directory

$gcs_bucket = curl.exe http://metadata/computeMetadata/v1/instance/attributes/bucket -H "Metadata-Flavor: Google"
$env:mount_path = $gcs_bucket, $gcs_bucket -join ":"

$env:vm_name = curl.exe http://metadata.google.internal/computeMetadata/v1/instance/hostname -H "Metadata-Flavor: Google"
$env:vm_name = ($env:vm_name -split "\.")[0]

curl.exe http://metadata/computeMetadata/v1/instance/attributes/rclone_conf -H "Metadata-Flavor: Google" > rclone.conf
(Get-Content -path .\rclone.conf) | Set-Content -Encoding UTF8 -Path .\rclone.conf

curl.exe http://metadata/computeMetadata/v1/instance/attributes/service_account -H "Metadata-Flavor: Google" > service-account.json
(Get-Content -path .\service-account.json) | Set-Content -Encoding ASCII -Path .\service-account.json

start powershell {.\rclone.exe mount $env:mount_path\TestFiles .\TestFiles --config=".\rclone.conf" --no-console --read-only}
Start-Sleep -Seconds 5

start powershell {.\rclone.exe mount $env:mount_path\TestData\ci-windows .\temp --config=".\rclone.conf" --no-console --read-only}
Start-Sleep -Seconds 5

start powershell {.\rclone.exe mount $env:mount_path\TestResults .\TestResultsRemote --config=".\rclone.conf" --no-console --read-only}
Start-Sleep -Seconds 5

start powershell {.\rclone.exe mount $env:mount_path\vm_data\$env:vm_name .\vm_data --config=".\rclone.conf" --no-console --read-only}
Start-Sleep -Seconds 5

Copy-Item -Path "temp\*" -Destination "."
Copy-Item -Path "TestResultsRemote" -Destination "TestResults" -Force -Recurse

powershell -command "Start-Process runCI.bat -Verb runas"
