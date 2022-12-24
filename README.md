Organize pics
=============
This program copies jpgeg files with jpg or JPG extensions into a year and subsequently year_month subfolder formatted as YYYY/YYYY_MM. In addition, it can be run as a server client. For performance reasons, the process is parallelized.

Open Ponts
----------

 - Why asyncio communication requires open/close for every transaction?
 - do I have to implement the RPC myself?
 - would flask a better solution if frontend would be javascript like?
 - is threading vs. asyncio well balanced?
 - how to implement browse for remote server?
 - are threads terminated correctly on abortion/close before done?
 - is closedir called from client before going to next directory? - done for happy path
 - handle and test opendir without closedir
 - test FileProcessor to actually perform copy or not depending on simulation
 - do I need a different function than asyncio.run when executing from a different thread?
 - use copy2 on server to not have files owned by root in the end - DONE
