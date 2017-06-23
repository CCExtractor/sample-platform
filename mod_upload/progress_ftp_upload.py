#!/usr/bin/python
import requests
import sys

if __name__ == '__main__':
    r = requests.post("serverurl/upload"
                      "/ftpupload?path=" + str(sys.argv[1]),
                      data={'path': str(sys.argv[1])}, verify=False)
