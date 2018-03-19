## Source code for analyzing the ideological slant of broadcast and cable News

Written for python 2.7, tested on Linux. Should run in cygwin on Windows. Should run on Mac.

Requires python packages: 
 - numpy
 - scipy
 - statsmodels
 - nltk (with English punkt tokenizer)
 - ujson, cPickle, bz2
 - unidecode

Includes congressmen IDs updated from Poole, Fox stoplist, and several measures of congressional ideology.

To run, requires pre-parsed monthly Closed Captioning (CC) files (produced by included parseNewsCCs.py file) in CCs/stationngrams, and scraped Congressional Record webpages in CR/data sorted by month and chamber.

From there, calling the bash script RUNALL.sh should run the whole analysis.