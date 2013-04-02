txwinrm
=======

Asynchronous Python WinRM client


Installation
------------

    $ python setup.py install


Basic Useage
------------

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

    cupertino ==> Select * From Win32_Process
                           addressing.Action http://schemas.xmlsoap.org/ws/2004/09/enumeration/PullResponse
                        addressing.MessageID uuid:60BE3E31-A195-4D33-9E95-5754695CC20F
                               addressing.To http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous
                        addressing.RelatesTo uuid:578DC055-B6C4-4387-B39F-E992D0ED76A0
                        -------------------- --------------------
                       Win32_Process.Caption dwm.exe
                   Win32_Process.CommandLine "C:\Windows\system32\Dwm.exe"
             Win32_Process.CreationClassName Win32_Process
    ...
                Win32_Process.WorkingSetSize 4538368
           Win32_Process.WriteOperationCount 0
            Win32_Process.WriteTransferCount 0
    ---------------------------------------- ----------------------------------------
                       Win32_Process.Caption explorer.exe
                   Win32_Process.CommandLine C:\Windows\Explorer.EXE
             Win32_Process.CreationClassName Win32_Process
    ...

A summary of the number of failures if any and number of XML elements processed
appears at the end. The '-d' option increases logging.

    There were 1 failures
    Processed 6823 elements


Performance of XML Parsers
--------------------------

Offers three XML parser implementations. Specify with the -p option.

    $ time python -m txwinrm.txwinrm -p sax >/dev/null
    Processed 9684 elements
    real    0m1.011s
    user    0m0.533s
    sys     0m0.113s

    $ time python -m txwinrm.txwinrm -p cetree >/dev/null
    Processed 9725 elements
    real    0m2.027s
    user    0m0.401s
    sys     0m0.140s

    $ time python -m txwinrm.txwinrm -p etree >/dev/null
    Processed 9684 elements
    real    0m1.501s
    user    0m1.192s
    sys     0m0.095s
