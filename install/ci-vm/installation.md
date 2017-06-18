# Installation guide for various platforms

This guide will give some hints and tips for configuring the VM's that will
run the CI setup.

Currently the guide covers Linux & Windows.

To reduce the required size of the VM's, as well as not having to update the 
VM template each time a sample changes, a network mount will be used to make
the data accessible towards the VM's. Setting up this network mount is not
covered in this guide.

## Linux

### Prerequisites

* Linux KVM with an distro of your choice
* CI user automatically logs in
* CI user has sudo rights to perform the `shutdown` command
* CCExtractor compiles successfully
* curl

### Adding the necessary services and files

#### runCI

* Copy over the `runCI` and `variables-sample` to a directory of choice. The 
next step assumes it's located in `/usr/src/ci/`, if this is not the case,
please **modify** the necessary files in the next step.
* Rename `variables-sample` to `variables`, and fill in variables
* Chmod both files so they can be executed.

#### Network folder

In case of the network mount, add the mount so that it's automatically 
connecting at start-up. E.g., for Debian/derivatives this can be added to 
`/etc/fstab`:

```
//127.0.0.1/repo /repo cifs user=<user>,pass=<password> 0 0
```

#### Startup service

* Copy `testsuite` to `/etc/init.d/testsuite`
* Chmod the file so it can be executed

## Windows

### Prerequisites

* Windows KVM with a Windows version of your choice
* CI user automatically logs in

### Compiling CCExtractor on Windows

Depending on the Windows version you'll have to install different compilers.

For Windows 10, you'll need VS2015 (platform 140), **with** XP support 
enabled for C++. You'll also need the VS2015 build tools.

### Adding the necessary services and files

#### Installing cURL

You can download cURL from https://curl.haxx.se/download.html, and to make
it callable through `curl` from the command line, this tutorial can be
followed: 
http://callejoabel.blogspot.in/2013/09/making-curl-work-on-windows-7.html

#### runCI

* Copy over the `runCI.bat` and `variables-sample.bat` to a directory of 
choice. The next step assumes it's located in `C:\Users\ci\Documents\ci`, 
if this is not the case, please **modify** the necessary files in the next 
step.
* Rename `variables-sample.bat` to `variables.bat`, and fill in variables

#### Network folder

In case of the network mount, it's best to have it connecting when the 
startup service is running.

#### Startup service

* Copy `startup.bat` to 
`C:\Users\ci\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`
