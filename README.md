txwinrm
=======

Asynchronous Python WinRM client


Installation
------------

You can run this application in place after checking it out from github, or
install it in your Python site libraries with:

    $ python setup.py install


Basic Useage
------------

    $ vim path/to/txwinrm/config.py
    $ python -m txwinrm.txwinrm

This will send WinRM enumerate requests to the hosts listed in
txwinrm/config.py. It will send a request for each WQL query listed in that
file. The output will look like

    <hostname> ==> <WQL query>
        <XML namespace hint>.<tag> <value>
        ...
        -------------------------- ---------------------------
        <XML namespace hint>.<tag> <value> (for next instance)
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

    $ python -m txwinrm.txwinrm >/dev/null

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


Performance of XML Parsers
--------------------------

Offers three XML parser implementations. Specify with the -p option.

    $ time python -m txwinrm.txwinrm -p sax >/dev/null
    Summary:
      Connected to 3 of 3 hosts
      Processed 14203 elements
      Failed to process 0 responses
      Peak virtual memory useage: 590724 kB
    real    0m2.223s
    user    0m0.851s
    sys     0m0.128s

    $ time python -m txwinrm.txwinrm -p etree >/dev/null
    Summary:
      Connected to 3 of 3 hosts
      Processed 14203 elements
      Failed to process 0 responses
      Peak virtual memory useage: 590692 kB
    real    0m3.104s
    user    0m1.790s
    sys     0m0.143s

    $ time python -m txwinrm.txwinrm -p cetree >/dev/null
    Summary:
      Connected to 3 of 3 hosts
      Processed 14203 elements
      Failed to process 0 responses
      Peak virtual memory useage: 588352 kB
    real    0m2.148s
    user    0m0.636s
    sys     0m0.139s
