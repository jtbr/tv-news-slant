# -*- coding: utf-8 -*-
# encoding=utf8  
import sys  

reload(sys)  
sys.setdefaultencoding('latin-1') #utf8
"""
Created on Tue Apr 15 20:03:59 2014

@author: Justin

Parses programs from selected stations in a directory of CC files, using the 
best feed available.
Cleans and tokenizes the text into bi- and tri- grams per station.

Input: directory of CC files named like KNTV_20160817_003000_NBC_Nightly_News.cc1.txt
Output: Date and station-filtered station n-gram file with n-gram usage counts 
    by station (STATIONNGRAMFILE)
Intermediates: CCFile list file with metadata for relevant CC files.
    Docs file if not using MongoDB or MongoDB records containing parsed CC files

NOTE: since CCs and NPR transcripts reside in separate dirs, the intake into Mongo must be
  run in two stages with different CCFiles.pickle to contain them.

NOTE: Run in three phases: 1) ingest and parse dir of NPR documents
  2) 200910 - 201012 CCs (with east coast stations), outputting station ngrams
  3) 201101 - 201512 CCs (with west coast affiliates), outputting station ngrams. 
  West doesnt come online until late 2010 and east runs into some issues after 2011.

"""
## IMPORTS

import os, re
from os import walk
import random
#from operator import itemgetter
from collections import defaultdict
from datetime import datetime,date
from unidecode import unidecode
from nltk.util import ngrams as nltk_ngrams
import nltk.data
from nltk.stem.porter import PorterStemmer
#import hunspell

sys.path.append('..') # add parent dir to import search path
# words missing from spellcheck (could keep counts of misspelled words and prioritize adding these)
from dict_additions import dict_additions
from common import stopwords, loadPickle, savePickle, mergeHashes, addNgrams, STATIONNGRAMFILE


### PARAMETERS ###

# flag to use spell checking/correction (turns out not to help much if at all in the end)
USE_SPELLCHECK = False
# flag to use mongodb (vs pickle file) for pre-processed documents
USE_MONGODB = True
# wipes mongodb before starting...
REBUILD_MONGODB = False
# flag to ignore any pickle files and regenerate data from scratch
REBUILD_DATA = False
# flag to update database with missing docs even if the CC_files aren't being rebuilt
UPDATE_DB = True

# take any BBC program broadcast on any channel (in practice, PBS), and create a 
# separate station from them
SEPARATE_BBC = True
# take any Al Jazeera program broadcast on any channel (in practice, LINKTV), and 
# add to ALJAZAM
SEPARATE_ALJZ = True # has the effect of extending series from 2012-03 to 2013-08 
# (and overlapping 2013-08 to 2013-10)
# TODO: Could check 2013-08 to 2013-10 period overlap to see if they're significantly different
REMOVE_COMEDIES = True # removes comedy programs from the networks (not COM)
REMOVE_PARTY_PROGRAMMING = True # removes state of the union, debates, conventions, inauguration

REMOVE_AD_TEXT = False # attempts to remove some ads caught by looking for signs that an ad is upcoming

# NOTE: RUN SEPARATELY for 2009Nov-2010Dec with east coast stations, and for 2011-present with west coast station map
# Date range for analysis of CCs, used as file filter:
MAX_DATE = date(2016,12,31)
MIN_DATE = date(2011,1,1)
# split station stats into months
years = ['2011','2012','2013','2014','2015', '2016']
months = ['{0:02d}'.format(month) for month in range(1,13)]

#Use east coast for 2009-10
#station_map = {'CNNW':'CNN', 'MSNBCW':'MSNBC', 'FOXNEWSW':'FOXNEWS','COMW':'COM', 
#    'WETA':'PBS', 'WJLA':'ABC', 'WUSA':'CBS', 'WRC':'NBC', 'BBCAMERICA':'BBC'} # exclude WTTG/FOX since it's just local news
#Use west coast affiliates, which avoid several errors in east coast affiliates after 2010
station_map = {'CNNW':'CNN', 'MSNBCW':'MSNBC', 'FOXNEWSW':'FOXNEWS','COMW':'COM', 
    'KQED':'PBS', 'KGO':'ABC', 'KPIX':'CBS', 'KNTV':'NBC', 'BBCAMERICA':'BBC'} 
# exclude WTTG/FOX since it's just local news
desired_stations = set(['CNN', 'CNBC', 'ALJAZAM', 'BLOOMBERG', 'MSNBC', 'COM', 
    'FOXNEWS', 'FBC', 'PBS', 'ABC', 'NBC', 'CBS', 'NPR', 'LINKTV', 'BBC']) 
    # Note BBC optionally split out later from PBS

### END PARAMETERS ###

if USE_MONGODB:
    from pymongo import MongoClient
#    from hashlib import md5
    MONGODB_PORT = 25541

ps = PorterStemmer()
sent_detector = nltk.data.load('tokenizers/punkt/english.pickle')
if USE_SPELLCHECK:
    speller = hunspell.HunSpell('/usr/share/hunspell/en_US.dic','/usr/share/hunspell/en_US.aff')
    for word in dict_additions:
        speller.add(word)


# Regular expression definitions

#notes = re.compile('=+\s?NOTE\s?=+.*=+\s?END\s?NOTE\s?=+', re.DOTALL | re.IGNORECASE)
#timestamps = re.compile('\n?\s*\{time\}.*$')
#indentedText = re.compile('^\s{4,}.*', re.MULTILINE) #>=4 char indent
#underlines = re.compile('_+')
#compactNewlines = re.compile('\n[\s\l\n]*\n')
#headers = re.compile('^{\sA-Z}*$') # line of all caps

cc_ext = re.compile('\.(cc\d)\.txt$')

# speakerHeader accepts: '>>>', '> Mr. Ryan:', 'Lourdes GARCIA-NAVARRA:', 'Unidentified Man #1:' (name parts must be 12 or fewer chars to avoid combinatorial time searches)
# The second possibility is newer and more flexible than the first (with >) but I left the first alone to avoid introducing bugs
speakerHeader = re.compile('^(?:>+(?:(\s*\w*\.?\s?\w*:)|))|^([\w\-#]{1,12}[\d\,\.]?\s?){1,4}:')
brackets = re.compile('\[+[^\[\]]*\]+') # would fail on [[something] not included]
parens = re.compile('\(+[^\(\)]*\)+')
symbolchars = re.compile(u'[\x0D\x0E]+|[\u2669-\u266f]+|\?\s+\?',flags=re.UNICODE)
repeatingChars = re.compile(r'(\w{1,3})\1{2,}') #chars or char-pairs occurring at least 3x in a row (findall will not work with this)
#almostAllCaps = re.compile('^[0-9A-Zthrdsn\$\s\.\,;!\?\-\"\'%/]+$')
startingLetter = re.compile('^(?![Ww][Oo]$)(?:([aAI]$)|([A-Za-z]{2,}))') # starts with 
    # a single letter word, or two lettes (excludes 'wo', "n't")

#This is seems to get about 80% ads, 20% false alarms
breakToAd = re.compile(r'((?:(?:coming up|on deck), [^\.]*?\.)|(?:in a (?:minute|moment), [^\.]*?\.)|' + \
    '(?:coming up\.)|(?:coming up .*? next\.)|(?:stay with us\.)|(?:stay tuned(?: for .*?| and .*?|)\.)|' + \
    '(?:(?:we\'ll|will) be (?:right | )back.*?\.)|(?:after this\.)|(?:quick break\.)|(?:that\'s next\.)|' + \
    '(?:keep it (?:right | )here.*?\.)|(?:these messages\.)|(?:when we (?:come back|return).*?\.)|' + \
    '(?:in (?:just | )a (?:moment|minute)\.)|(?:moments away\.)|(?:brought to you by)|' + \
    '(?:back in a (?:minute|moment).*?\.)|(?:back in (?:two|three|2|3)(?: minutes|)\.)|' + \
    '(?:after (?:the|this) break.*?\.)|(?:(?:right|next|ahead) (?:here | )on ".*?\.)|' + \
    '(?:(?:we will|we\'ll|we are|we\'re|more) [^\.]*? next\.)|(?:just ahead\.)|' + \
    '(?:funding [^\.]*?provided by.*?\.)|(?:brought to you by.*?\.))', 
         flags=re.IGNORECASE) # .*? is a minimal match of any character (not greedy)
#issues:
#  ads containing announcers will remain after omitting these...
#  "coming up, .*" is a bit broad
#  'ANDERSON IS BACK IN A MOMENT. I'M SUSAN HENDRICKS WITH A "360" NEWS AND BUSINESS BULLETIN.'
#  'THIS IS A STORY THAT IS STRANGER THE MORE WE LOOK INTO IT. IT'S A LONG STORY BUT STAY WITH US. ON TUESDAY THE SENATE REJECTED'
# (?:this is ".*?\.)|(?:(?:you\'re|you are) watching ".*?\.)| - not used because often at beginning/middle of shows too.

#double checked all programs Oct 7 2016:
# local programs to omit:
localprog = re.compile('(?:ABC\s?7)|(?:Washington)|(?:wusa\s?9)|(?:9News\s?Now)|(?:Eyewitness)|' + \
    '(?:KQED)|(?:California)|(?:News\s?4)|(?:NBC\s?Bay)|(?:News\s?at\s?\d)|(?:Bay)|' + \
    '(?:Press\s?Here)|(?:KPIX\s?5)|(?:CBS\s?5)|(?:Mosaic)|(?:Up\s?to\s?the\s?Minute)|' + \
    '(?:To\s?the\s?Contrary)|(?:Assignment\s?7)|(?:Beyond\s?the\s?Headlines)|' + \
    '(?:Action\s?News)', flags=re.IGNORECASE) # (?: ...) is non-capturing parentheses
    
# coverage of events not produced by stations and potentially biased:
partyprog = re.compile('(?:Convention)|(?:Inauguration)|(?:State of the Union)|' + \
    '(?:(?<!Post[\s\-])(?<!Pre[\s\-])(?<!Great )(?<!Davos )Debate(?!\sAnalysis)(?!\sPreview))',
    flags=re.IGNORECASE) # NOTE: CNN has a regular program called State of the Union that should not be excluded

# late night comedy programs (not COM)
comedy = re.compile('(?:Jimmy Kimmel Live)|(?:The Tonight Show)|(?:The Late Show)|(?:Late Night)')

def nextmonth(month,year):
    """return YYYYMMDD str for first day of next month, given month, year as strings"""
    month = int(month)+1
    if month==13:
        month=1
        year = str(int(year)+1)
    month = '{0:02d}'.format(month)
    return year+month+'01'

def fullLineParse(line):
    """remove peculiarities and trim line"""

    line = brackets.sub('',line) # remove [ Male Announcer ], eg.
    line = parens.sub('',line) # remove (LAUGHTER), eg.
    line = symbolchars.sub('', line) # remove symbols
    line = repeatingChars.sub('', line) # remove sequences of 3+ chars/pairs of chars
    
    if REMOVE_AD_TEXT:
        splitline = breakToAd.split(line)
        if len(splitline)>1:
            print "  dropped (Ad?): "+splitline[-1]
            # remove apparent ads along with ad-break-signifying text:
            line = ''.join(splitline[0:-1])
            # could instead just add a newline before the apparent ads (still drops ad-break-signifying text)
            #line = '\n'.join([ ''.join(splitline[0:-1]), splitline[-1] ])

    #split line on music signifier, often used before ads
    #line.replace('\xe2\x99\xaa','\n')        
    return line.strip()

def hasNLines(N,filestr):
    """returns true if the filestr has at least N lines and N periods (~sentences)"""
    lines = 0
    periods = 0
    for line in filestr:
        lines = lines+1
        periods = periods + len(line.split('.'))-1
        if lines >= N and periods >= N:
            return True;
    return False;
    
def parse(prog):
    """Parse the program, separating into lines by speaker
    
    prog is a tuple: ((dirpath,station,airdate,airtime,progname),[ccstreamlist])
    """
    (progtuple,ccs) = prog
    print prog
    (dirpath,name,station,airdate,airtime,progname) = progtuple
    #'name' is the filename without extensions
    # choose the best CC, or rather the first that is above MINSIZE
    MINSIZE = 400
    ccs.sort() # we want to try 1 first. 3 is often foreign language
    enough_lines = False    
    for ccstream in ccs:
        filename = ".".join([name,ccstream,'txt'])
        fullpath = os.path.join(dirpath,filename)
        with open(fullpath,'r') as f:
            filestr = f.read()
        enough_lines = hasNLines(5, filestr)
        if len(filestr)>=MINSIZE and enough_lines:
            break
    
    if len(filestr)<MINSIZE or not enough_lines:
        print "Error: " + filename + " has no CC above MINSIZE"
        return
    if not isinstance(filestr,str):
        print "ERROR: " + filename + " not an acceptable CC stream"
        return

    docBody = ''
    nextline = ''    
    for line in filestr.splitlines():
        if len(line)==0:
            continue
        if line[0] == '[' or (len(line)>3 and line[3] == '['): #first line may contain 3ch sequence
            line = line[line.find(']')+2:] #drop time signature; works even if there isn't one
        line = parens.sub('', line) #remove possible qualifiers in speaker header (and elsewhere)
        if speakerHeader.match(line): #Next Speaker
            nextline = fullLineParse(nextline)
            if (nextline): 
                docBody += nextline + '\n'
            nextline=''         
            line = speakerHeader.sub('',line) #remove speaker header
        
        # letters remain in the line
        nextline = " ".join([nextline, line.strip()])
        
    # after reaching end of file, add remaining line, if any
    if (nextline): 
        docBody += fullLineParse(nextline) + '\n'

    #print filename + ' (' + airdate + '): ...\n' + docBody
    #alternatively: docBody.decode('cp1252').encode('ascii','ignore')
    docBody = unidecode(docBody) # speeches separated by newlines
    return {'filename': name, 'station': station, 'airdate': airdate, 
        'airtime': airtime, 'progname': progname, 'docBody': docBody};


correctedWords = set()
def spcorrect(word):
    """Return the word or the most likely correction of it"""
    #return word if speller.spell(word) else speller.suggest(word)[0]
    try:
      if speller.spell(word):
        return word
      else:
        correctedWords.add(word)
        try:
            correction = speller.suggest(word)[0]
#            print "replacing " + correction + " for " + word
            return correction
        except:
            print "no corrections for " + word
            return word
    except:
        print "wtf?: dropping " + word
        return ''

def tokenize(program_ccs):
    """Split document into bigrams and trigrams on a sentence by sentence basis, 
    after optionally spellchecking, dropping stopwords, nonwords, & extra-long words, 
    and stemming, then aggregate into counts of unique bi/tri-grams"""
    bigrams = defaultdict(int)
    trigrams = defaultdict(int)
    # process by lines (speakers)
    for line in program_ccs.splitlines():
        #TODO: remove ads (?)
#        splitline = breakToAd.split(line)
#        if len(splitline)>1:
#            line = ''.join(splitline[0:-1]) # drop after the last upcoming ad marker

        sentences = sent_detector.tokenize(line)
        for sentence in sentences:
            sentence = sentence.lower()
            words = nltk.tokenize.word_tokenize(sentence)
            # drop 's, numbers, punctuation, etc (and long words -wtf?)
            words = [word for word in words if 
                        (startingLetter.match(word) and len(word)<20 and word not in stopwords)]
            if USE_SPELLCHECK: 
                words = [spcorrect(word.upper()).lower() for word in words] # correct spelling
            stems = [ps.stem(word) for word in words] # stem words
            
            addNgrams(bigrams, nltk_ngrams(stems,2))
            addNgrams(trigrams, nltk_ngrams(stems,3))

    #print len(bigrams)
    #print bigrams
    #print len(trigrams)
    return (bigrams, trigrams)

def tokenizeAndJoin(doc,all_ngrams,programs):
    """Tokenize a document and add bi-trigram counts to the appropriate station"""
    station = doc['station']
    airdate = doc['airdate']
    progname = doc['progname']
    docBody = doc['docBody'].encode('ascii','ignore')
    if not station in desired_stations:
        #this should be redundant
        return

    print "  Processing: " + station + "  " + progname + "- " + airdate

    # ignore things that aren't where they should be
    #include WSJ on CNBC only (not carried nationally on any other network)
    #some PBS found in WUSA (CBS)
    #some CBS found in KNTV (NBC) (they appear to be NBC but may be non-news or local in some cases)
    #some found in KNTV (all sports or ads)
    if (station!='CNBC' and progname.find('Wall Street Journal')>=0) or \
       (station=='CBS' and progname in programs['PBS']) or \
       (station=='NBC' and progname in programs['CBS']) or \
       (station=='NBC' and (progname.find('BBC')>=0 or progname.find('Frontline')>=0 or progname.find('McLaughlin Group')>=0)): 
        print "   - Skipping."
        return # skip/ignore

    # ignore optional categories as requested
    if REMOVE_COMEDIES and comedy.findall(progname):
        print "   - Skipping comedy."
        return # ignore it
    if REMOVE_PARTY_PROGRAMMING and partyprog.findall(progname):
        if not (station=='CNN' and progname == 'State of the Union'): #regular program
            print "   - Skipping non-station (party) programming"
            return # ignore it

    (bigrams, trigrams) = tokenize(docBody)

    # special cases:
    if SEPARATE_BBC and progname.find('BBC')>=0:
        print "   - Allocating program to BBC station."
        station = 'BBC'
    if SEPARATE_ALJZ and progname.find('Al Jazeera')>=0:
        print "   - Allocating program to Al Jazeera station."
        station = 'ALJAZAM'
    

    try:
        (station_bigrams,station_trigrams) = all_ngrams[station]
        mergeHashes(station_bigrams,bigrams)
        mergeHashes(station_trigrams,trigrams)
    except: #it's the first set of ngrams for this station
        all_ngrams[station] = (bigrams,trigrams)

def main(args):
    if len(args)<2:
        print "USAGE: parseNewsCCs <ccFilePath>"
        return
        
    CCFILELISTFILE = 'CCfiles.pickle'
    DOCFILE = 'docs.pickle'
    
    global REBUILD_DATA
    
    random.seed(a=1) # seed randomizer for predictability
    startpath = args[1]

    if USE_MONGODB:
        mclient = MongoClient('localhost', MONGODB_PORT)
        mdb = mclient.ccdb
        if REBUILD_MONGODB:
            mdb.docs.drop()
        mdocs = mdb.docs
        mdocs.ensure_index('filename', unique=True) #creates index if not already there
        mdocs.ensure_index('airdate')
    
    ccfiles = not REBUILD_DATA and loadPickle(CCFILELISTFILE)
    if not ccfiles:
        REBUILD_DATA = True
        print 'Loading CC filenames in '  + startpath + "...\n"
        stations = set()
        programs = defaultdict(set) # equivalent to lambda: set([])
        program_ccs = defaultdict(list) # equivalent to lambda: []
        ## find all files under startpath
        for (dirpath, dirnames, filenames) in walk(startpath):
            for f in filenames:
                name = cc_ext.sub('',f)
                nameparts = name.split('_')
                ccnum = cc_ext.findall(f)
                if not ccnum:
                    #print "unexpected filename: " + f
                    continue
                ccnum = ccnum[0]
                station = nameparts[0]
                airdate = nameparts[1]
                airtime = nameparts[2]
                progname = " ".join(nameparts[3:])
                d = datetime.strptime(airdate, "%Y%m%d").date()
                if d<MIN_DATE or d>MAX_DATE:
                    continue #ignore it
                stations.add(station)
                station = station_map.get(station,station) #replace eg CNNW w/ CNN
                programs[station].add(progname)
                if (station in desired_stations):
                    if not localprog.findall(progname): #ignore local programming (always)
                        program_ccs[(dirpath,name,station,airdate,airtime,progname)].append(ccnum)
        
        print stations
        print programs
        ccfiles = (program_ccs,stations,programs)
        savePickle(CCFILELISTFILE,ccfiles)
    
    (program_ccs,stations,programs) = ccfiles
    docs = not REBUILD_DATA and loadPickle(DOCFILE)
    if REBUILD_DATA or UPDATE_DB or (not USE_MONGODB and not docs):
        REBUILD_DATA = True
        print "Loading and pre-processing files ... "
        ## parse and cleanse documents, saving them as a set
        docs = []
        items = program_ccs.items()
#        random.shuffle(items)
        for prog in items:
            if (USE_MONGODB and mdocs.find_one({'filename':prog[0][1]},{})):
                #a docBody for this filename already exists in database; skip
                continue
            parsedDoc = parse(prog)
            if parsedDoc:            
                if USE_MONGODB:
                    mdocs.insert(parsedDoc) #or save()?
                else:
                    docs.append(parsedDoc)
#            if len(docs)>40:
#                break
        #print docs
        if not USE_MONGODB: 
            savePickle(DOCFILE,docs)
    
    # generate bi- and tri-grams for each station
    print "Generating n-grams for all programs and arranging them by station..."
    for year in years:
        for month in months:
#            if year=='2014' and int(month)>6: break  #TEMP!
            fn = year+month+"_"+STATIONNGRAMFILE
            all_station_ngrams = not REBUILD_DATA and loadPickle(fn)
            if not all_station_ngrams:
                all_station_ngrams = {}
                gte_date = year+month+'01'
                lt_date = nextmonth(month,year)
                print "######## Working on month beginning " + gte_date + " ########"
                if USE_MONGODB:
                    for doc in mdocs.find({"airdate": {"$gte": gte_date, "$lt": lt_date}}):
                        tokenizeAndJoin(doc, all_station_ngrams, programs)
                else:
                    for doc in docs:
                        tokenizeAndJoin(doc, all_station_ngrams, programs)
                savePickle(fn, all_station_ngrams)
                

    if USE_SPELLCHECK:
        print list(correctedWords)
        savePickle('corrected.pickle',correctedWords)

#    print sorted(all_station_ngrams['FOXNEWSW'][0].viewitems(),key=itemgetter(1),reverse=True) # sort on counts
# get counts of bgrams and trigrams for station
#sum([count for count in all_station_ngrams['ABC'][0].values()]) # station's bigrams
#sum([count for count in all_station_ngrams['ABC'][1].values()]) # station's trigrams
#total bigrams for month:
#sum([count for station in all_station_ngrams.keys() for count in data[station][0].values()])

    print "Done!"
    
if __name__ == "__main__":
    main(sys.argv)
    