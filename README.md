txwinrm
=======

Asynchronous Python WinRM client


Current Feature Support
-----------------------

* HTTP
* Basic authentication
* WQL queries


Future Feature Support
----------------------

* WinRS
* PerfMon over WinRS
* Subscribe to the Windows Event Log
* Kerberos authentication (domain accounts)
* NTLM authentication (local accounts)
* HTTPS


Installation
------------

Install this application into your Python site libraries with:

    $ python setup.py install


Dependencies
------------

Python 2.7
Twisted 11.0 or later (utilizes HTTP connection pools with Twisted 12.1 or later)


Configuring the Target Windows Machines
---------------------------------------

You can enable the WinRM service on Windows Server 2003, 2008 and 2012. Run
Command Prompt as Administrator and execute the following commands

    winrm quickconfig
    winrm s winrm/config/service @{AllowUnencrypted="true"}
    winrm s winrm/config/service/auth @{Basic="true"}


Basic Useage
------------

You can pass a single host and query via the command line...

    $ winrm -r host -u user -p passwd -f "select * from Win32_NetworkAdapter"


..., or create an ini-style config file and hit multiple targets with multiple
queries. Example config is at examples/config.ini

    $ winrm -c path/to/config.ini


This will send WinRM enumerate requests to the hosts listed in config.ini. It
will send a request for each WQL query listed in that file. The output will
look like

    <hostname> ==> <WQL query>
        <property-name> = <value>
        ...
        ---- (indicates start of next item)
        <property-name> = <value>
        ...
    ...


Here is an example...

    cupertino ==> Select name,caption,pathName,serviceType,startMode,startName,state From Win32_Service
      Caption = Application Experience
      Name = AeLookupSvc
      PathName = C:\Windows\system32\svchost.exe -k netsvcs
      ServiceType = Share Process
      StartMode = Manual
      StartName = localSystem
      State = Stopped
      ----
      Caption = Application Layer Gateway Service
      Name = ALG
    ...


A summary of the number of failures if any and number of XML elements processed
appears at the end. The summary and any errors are written to stderr, so
redirect stdin to /dev/null if you want terse output.

    $ winrm -c path/to/config.ini >/dev/null

    Summary:
      Connected to 3 of 3 hosts
      Processed 13975 elements
      Failed to process 0 responses
      Peak virtual memory useage: 529060 kB

      Remote CPU utilization:
        campbell
          0.00% of CPU time used by WmiPrvSE process with pid 1544
          4.00% of CPU time used by WmiPrvSE#1 process with pid 1684
          4.00% of CPU time used by WmiPrvSE#2 process with pid 3048
        cupertino
          0.00% of CPU time used by WmiPrvSE process with pid 1608
          3.12% of CPU time used by WmiPrvSE#1 process with pid 1764
          9.38% of CPU time used by WmiPrvSE#2 process with pid 2608
        gilroy
          1.08% of CPU time used by WmiPrvSE process with pid 1428
          5.38% of CPU time used by WmiPrvSE#1 process with pid 1760
          4.30% of CPU time used by WmiPrvSE#2 process with pid 1268


The '-d' option increases logging, printing out the XML for all requests and
responses, along with the HTTP status code.
