# -*- coding: utf-8 -*-
"""
Created on Tue Apr 15 20:03:59 2014

Compiles the speeches for each congressman (excluding other text), constructs 
them into n-grams, counts them and aggregates by party.

Input: years, scraped CR files under CR/data/(year)/House|Senate/(monthnums)/
Intermediates: Doc file containing parsed CR files,
    speech file with all speeches for each congressman
    congressman file with lookup table for all congressmen's possible names
    congressmen n-gram file with n-grams for each
    congressmen statistics pickle and CSV files with statistics about each 
        congressman's speeches.
Outputs: All n-grams file with n-grams by party,
    n-gram chisq file with counts, chisq scores for each n-gram

@author: Justin
"""

import os, sys, re, csv, random, math
from os import walk
from operator import itemgetter
from collections import defaultdict
from HTMLParser import HTMLParser
from datetime import datetime, date
from nltk.util import ngrams as nltk_ngrams
import nltk.data
from nltk.stem.porter import PorterStemmer
import countsyl

from read_icpsr_member_ids import readICPSRFile

sys.path.append('..') # add parent dir to import search path
from common import stopwords, omitted_phrases, omitted_bigrams, loadPickle, savePickle, mergeHashes, addNgrams, \
        CONGRESSMENNGRAMFILE, CONGRESSMENSTATSFILE, ALLCRNGRAMFILE, NGRAMCHISQFILE

# flag to ignore any pickle files and regenerate data from scratch
REBUILD_DATA = False

ps = PorterStemmer()
sent_detector = nltk.data.load('tokenizers/punkt/english.pickle')

SENTENCE_COUNT = 0
WORD_COUNT = 0

singleBrackets = re.compile('\n?\s*\[[^\[\]]*\]\n?')
notes = re.compile('=+\s?NOTE\s?=+.*=+\s?END\s?NOTE\s?=+', re.DOTALL | re.IGNORECASE)
timestamps = re.compile('\n?\s*\{time\}.*$')
indentedText = re.compile('^\s{4,}.*', re.MULTILINE) #>=4 char indent
underlines = re.compile('_+')
multidotsdashes = re.compile('[\.-]{2,}')
singleParens = re.compile('\([^\(\)]*\)', re.DOTALL)
compactNewlines = re.compile('\n[\s\l\n]*\n')
mrPresident = re.compile('(?:[Mm]rs?\.?|[Mm]adame?)\s*(?:[Ss]peaker|[Pp]resident)\,?') # could be removed via bigrams list now...
headers = re.compile('^{\sA-Z0-9}*$') # line of all caps with possible #'s
# Dr/Mr/Mrs/Ms. McNAME-LONGNAME of Nevada. | The ACTING PRESIDENT pro tempore. 
#SpeakerName = re.compile('^  (?:(?:[DM][rR]?[sS]?\.)|(?:The)) ([A-Zces\- ]{2,}(?:(?:(?:(?:\. [A-Zces\- ]{2,} )|(?: ))[Oo]f [\w]+\s?(?!and)(?!for)\w*){0,1}|(?: pro tempore){0,1}))\s?\.', re.MULTILINE)
SpeakerName = re.compile('^  (?:(?:[DM][rR]?[sS]?\.)|(?:The)) ((?:[A-Zces\-]{2,}\s?){1,4}(?:(?:[A-Z]\. (?:[A-Zces\-]{2,}\s){1,2})|)(?:(?:[Oo]f [\w]+\s?(?!and)(?!for)\w*){0,1}|(?:pro tempore){0,1}))\s?\.', re.MULTILINE)
#                            [Prefix                        ] ([1-4 2+ltr ALLCAP words  ][?a middle initial and a lastname        ][?of statename or state name              ]|[?pro tempore        ].

def nextmonth(month,year):
    """return date for first day of next month, given month, year as strings"""
    month = int(month)+1
    year = int(year)
    if month==13:
        month=1
        year = year+1    
    return date(year,month,1)

# extend HTMLParser class
class MyHtmlParser(HTMLParser):
    """Parse HTML of CR files; save document body and date"""
    inPre=False; inTitle=False;
    docDate=date.min
    docBody=''
    def handle_starttag(self,tag,attrs):
        if tag=='pre':
            self.inPre=True;
        elif tag=='title':
            self.inTitle=True;
    def handle_endtag(self,tag):
        if tag=='pre':
            self.inPre=False
        elif tag=='title':
            self.inTitle=False
    def handle_data(self,data):
        if self.inPre:  # these documents have the entire body within a <pre> block
            self.docBody += data
        elif self.inTitle:
            # find parenthesized date and strip parens            
            dateStr = re.search('\([^\)]*\)',data).group()[1:-1]; 
            #print "'" + dateStr + "'";
            self.docDate = datetime.strptime(dateStr,'%A, %B %d, %Y').date();
        

def parse(filename):
    """Parse CR file, returning the filename, date and parsed document body
    
    Parsing removes unwanted text (double brackets, header lines, timestamps, notes, 
    indented text/quotes, underlines (section separators), parentheticals. It 
    compacts multiple dashes and dots, and multiple newlines.
    """
    f = open(filename,'r')
    filestr = f.read()
    f.close();
    
    htmlParser = MyHtmlParser()
    htmlParser.feed(filestr) # parse out date and drop all other tags
    docBody = htmlParser.docBody
    docDate = htmlParser.docDate
    htmlParser.close();
    
    #drop unwanted text
    docBody = singleBrackets.sub('', docBody)
    docBody = singleBrackets.sub('', docBody) # rid double brackets, mostly page numbers
    docBody = headers.sub('',docBody) # lines of all caps
    docBody = notes.sub('', docBody)  # occasional note sections normally listing changes to the record
    docBody = timestamps.sub('', docBody)
    docBody = indentedText.sub('', docBody) # all sorts of non speech, like text of bills
    docBody = underlines.sub('', docBody)  # section seperators
    parentheticals = singleParens.findall(docBody)
    if parentheticals:
#        print 'Found parens: ' + str(parentheticals) # stenographers notes and metadata about what's happening
        docBody = singleParens.sub('', docBody)
        docBody = singleParens.sub('', docBody) # rid enclosed parentheticals

    docBody = multidotsdashes.sub(' ', docBody) # convert multi dots/dashes to a space
    docBody = mrPresident.sub('', docBody) # remove references to mr/madame president/speaker
    docBody = compactNewlines.sub('\n', docBody)
    
    #print filename + ': ' + docDate.isoformat() + '...\n' + docBody
    return (filename, docDate, docBody);
        
# Calculate approximate using SMOG: http://en.wikipedia.org/wiki/SMOG over 
# a sample of 30-120 sentences
def findGradeLevel(sentences):
    gradeLevel = 0.0
    if len(sentences)>30:  # 30 is the minimum number of sentences for a valid measure
        sampleSz = min(len(sentences),120)
        sentenceSample = [sentences[i] for i in random.sample(xrange(len(sentences)), sampleSz)]
        minPolySyllables = 0
        maxPolySyllables = 0        
        for sentence in sentenceSample:
            sentence = sentence.lower()
            words = nltk.tokenize.word_tokenize(sentence)
            for word in words:
                (minsyl,maxsyl) = countsyl.count_syllables(word)
                if minsyl>=3: 
                    minPolySyllables += 1
                    maxPolySyllables += 1
                elif maxsyl>=3:
                    maxPolySyllables +=1
        polySyllables = minPolySyllables *.66 + maxPolySyllables *.34
        gradeLevel = 1.043 * math.sqrt(polySyllables * 30.0 / sampleSz) + 3.1291
        return gradeLevel

def tokenize(speeches):
    """Tokenize a set of speeches, returning the counts of bigrams & trigrams 
    used and statistics about each speaker"""
    # make speeches a big long string if it isn't already
    if type(speeches)==list:
        speeches='\n'.join(speeches)
    bigrams = defaultdict(int)
    trigrams = defaultdict(int)
    startingLetter = re.compile('^[a-z]')
    speakerStats = {}
    speakerWordCount = 0
    
    ## first remove stop words
    sentences = sent_detector.tokenize(speeches)
    global SENTENCE_COUNT
    SENTENCE_COUNT += len(sentences)
    for sentence in sentences:
        sentence = sentence.lower()
        words = nltk.tokenize.word_tokenize(sentence)
        words = [word for word in words if startingLetter.match(word)] # drop 's, numbers, punctuation, etc
        speakerWordCount += len(words)
        words = [word for word in words if word not in stopwords] # drop stopwords
        stems = [ps.stem(word) for word in words] # stem words

        addNgrams(bigrams, nltk_ngrams(stems,2))
        addNgrams(trigrams, nltk_ngrams(stems,3))

    #print len(bigrams)
    #print bigrams
    #print len(trigrams)

    #this is also a good place to analyze language complexity using SMOG
    speakerStats['gradeLevel'] = findGradeLevel(sentences)
    speakerStats['sentences'] = len(sentences)
    speakerStats['words'] = speakerWordCount
    
    global WORD_COUNT
    WORD_COUNT += speakerWordCount
    # In case speeches are really short & have no bi/tri grams
    return ((bigrams, trigrams), speakerStats) if bigrams and trigrams else None

def addNamePermutations(congressmanTuple, nameToID):
    """Derive possible permutations of the congressman's name as used in the CR, 
    and add these to the nameToID map"""
    (__, ICPSRMemberID, StateAbbr, StateName, DistrictNum, PoliticalParty,
         __, LongName) = congressmanTuple    
    statemodifier = ' OF ' + StateName.upper()
    names = LongName.split(',')
    lastname = names[0]
    if len(names)<2: print names
    fullfirstname = names[1].strip() # in some cases hay names[2], eg. ", Jr." which we ignore
    lastnames = lastname.rsplit(' ',1) #remove suffixes "III" or "Jr."
    if len(lastnames)>1:
        lastname =  lastname if lastnames[1].find('.')<0 and lastnames[1].find('II')<0 else lastnames[0]   
    firstnames = fullfirstname.split() # drop middle name/initial, unless abbreviated first name (D. Bernard)
    firstname =  firstnames[0] if firstnames[0].find('.')<0 else firstnames[1]
    fullname = firstname + ' ' + lastname # remove middle initials?
    veryfullname = fullfirstname + ' ' + lastname
    #print LongName + " -> " + fullname
    hashvalue = (ICPSRMemberID, StateAbbr, StateName, DistrictNum, PoliticalParty, fullname)
    nameToID[lastname] = hashvalue
    nameToID[lastname + statemodifier] = hashvalue
    nameToID[fullname] = hashvalue
    nameToID[fullname + statemodifier] = hashvalue
    if veryfullname != fullname:
        nameToID[veryfullname] = hashvalue
        nameToID[veryfullname + statemodifier] = hashvalue
    #two exceptions stemming from differences in CR and member list spellings:
    if fullname == 'DAN LUNGREN':
        nameToID['DANIEL E. LUNGREN OF CALIFORNIA'] = hashvalue
    elif fullname == 'SHEILA JACKSON-LEE':
        nameToID['JACKSON LEE OF TEXAS'] = hashvalue
        nameToID['JACKSON LEE'] = hashvalue
    elif LongName == 'DOYLE, MIKE F.':
        nameToID['MICHAEL F. DOYLE OF PENNSYLVANIA'] = hashvalue

def main(args):
    years = []
    month = None # unset month ==> combine all provided years. year and month provided ==> process just that month
    if len(args) < 2:
        print 'no year(s) passed in as parameter! Exiting.'
        exit()
    else:        
        i=1  # allow specifying multiple (consecutive) years; first arg is script name
        while i < len(args):
            if (i==2 and int(args[i])<1800):
                # will run for single month
                month = args[i] # should be provided as 2-digit month, eg '03'
            else:
                # will run for multiple years as one run
                years.append(args[i])
            i+=1
        
    year_prefix = years[0]
    output_prefix = ""
    if len(years)>1:
        year_prefix += '-' + years[-1][-1:] # last year take (only) 1 digit eg 2013-4
        output_prefix = year_prefix
    elif month:
        year = years[0]
        output_prefix = year + month # eg 201308
        
    
    # these apply to the whole year when running monthly (and are re-used with REBUILD_DATA=False)
    # and to the whole period when running yearly/multi-year
    DOCFILE= year_prefix+'docs.pickle'
    SPEECHFILE= year_prefix+'speeches.pickle'
    CONGRESSMENFILE = year_prefix+'congressmen.pickle'
    
    # these outputs are for the specified period (either one month, one year or multiple years)
    global CONGRESSMENNGRAMFILE, CONGRESSMENSTATSFILE, ALLCRNGRAMFILE, NGRAMCHISQFILE, REBUILD_DATA
    CONGRESSMENNGRAMFILE = output_prefix+CONGRESSMENNGRAMFILE
    CONGRESSMENSTATSFILE = output_prefix+CONGRESSMENSTATSFILE
    CONGRESSMENSTATSCSVFILE = output_prefix+'congressmenstats.csv'    
    ALLCRNGRAMFILE = output_prefix+ALLCRNGRAMFILE
    NGRAMCHISQFILE = output_prefix+NGRAMCHISQFILE
    
    # load documents in the congressional record for given year(s)
    docs = not REBUILD_DATA and loadPickle(DOCFILE)
    if not docs:
        REBUILD_DATA = True
        docs = []
        for year in years:    
            startpath = os.path.join('data',year)
        
            print "Loading and pre-processing files in " + startpath + "...\n"
            fns = []
            ## find all files under startpath
            for (dirpath, dirnames, filenames) in walk(startpath):
                fns += [os.path.join(dirpath,f) for f in filenames];
        
            ## parse and cleanse documents, saving them as a set
            for fn in fns:
                docs.append( parse(fn) ) # (saves tuple: filename, docDate, docBody)
            savePickle(DOCFILE,docs)
        #print docs
    
    
    # assign speeches to speakers
    speeches = not REBUILD_DATA and loadPickle(SPEECHFILE)
    if not speeches:
        REBUILD_DATA = True
        print "Parsing speeches to speakers..."
        speeches = {};  
        for filename, docDate, docBody in docs:
            #filename, docDate, docBody  = doctuple;
            speakers = SpeakerName.split(docBody)
            #structure: [<content prior to 1st speaker>, <1st speaker>, <1st speech>, <2nd speaker>, <2nd speech>, ...]
            if len(speakers)>1:
                condenseWhitespace = re.compile('\s+')
                for i in reversed(range(2,len(speakers),2)): #eg, 6,4,2
                    speaker = speakers[i-1].upper().strip()
                    speech = condenseWhitespace.sub(' ', speakers[i]).strip()
                    speakers_speeches = speeches.get(speaker,[])
                    speakers_speeches.append((filename,docDate,speech)) #save speech to speaker's list of speeches
                    speeches[speaker] = speakers_speeches
    #        else:
    #            print 'No Speakers:'
    #            print filename + ': ' + docDate.isoformat() + '...\n' + docBody
                
        #print speeches
    #    speakers = speeches.keys()
    #    speakers.sort()
    #    print speakers
        savePickle(SPEECHFILE,speeches)


    # TODO: Handle cross-session years
    # starting from the 83rd congress in 1953-1954, sessions were only in 2 calendar years
    def getCongress(yr):
        return int((int(yr) - 1953)/2) + 83

    CONGRESSES = set()
    for yr in years:
        CONGRESSES.add(getCongress(yr))    

    # find all possible permutations of congressmen's names in the CR
    NameToIDMap = not REBUILD_DATA and loadPickle(CONGRESSMENFILE)
    if not NameToIDMap:
        REBUILD_DATA = True
        print "Reading and processing congressmembers..."
        NameToIDMap = {}
        house_members = readICPSRFile('h01114nw.txt')
        for member in house_members:
            if member[0] in CONGRESSES:
                addNamePermutations(member,NameToIDMap)
        senators = readICPSRFile('s01114nw.txt')
        for senator in senators:
            if senator[0] in CONGRESSES:
                addNamePermutations(senator,NameToIDMap)
        savePickle(CONGRESSMENFILE,NameToIDMap)

    speaker_ngrams = not REBUILD_DATA and loadPickle(CONGRESSMENNGRAMFILE)
    if not speaker_ngrams:
        REBUILD_DATA = True
        # generate bi- and tri-grams for each speaker    
        print "Generating n-grams for each speaker..."
        speaker_ngrams = {}
        speaker_stats = {}
        for (speaker, speechtuples) in speeches.viewitems():
            try:
                congressman = NameToIDMap[speaker]
                #print 'Speaker found for: ' + speaker
            except:
                if speaker.find('SPEAKER')<0 \
                    and speaker.find('PRESIDENT')<0 \
                    and speaker.find('PRESIDING')<0 \
                    and speaker.find('CHAIR')<0:
                    print 'Unable to find speaker: ' + speaker + ' with ' \
                        + str(len(speechtuples)) + ' speeches'
                    # these should amount to the non-voting delegates & former 
                    # representatives, plus a few mis-spelled names
                continue
            if month:
                # skip all speeches outside the selected month
                gte_date = date(int(year),int(month),1)
                lt_date = nextmonth(month,year)
                all_speeches = [speech for (filename,spdate,speech) in speechtuples if 
                                    (spdate >= gte_date and spdate < lt_date)]
            else:
                all_speeches = [speech for (filename,spdate,speech) in speechtuples]
            retval = tokenize(all_speeches)
            if retval:
                (ngrams, speechStats) = retval
                speechStats['speeches'] = len(speechtuples) #  #/times recognized to speak
                speechStats['congressman'] = congressman
                print 'Congressman ' + speaker + ' has calculated grade level: ' \
                       + str(speechStats['gradeLevel']) + ' from ' \
                       + str(speechStats['sentences']) + ' sentences.'
                speaker_stats[congressman] = speechStats
                speaker_ngrams[congressman] = ngrams
            else: 
                #in 2012, Gabby Giffords said only "I miss you."; this needs skipping
                print "Unable to tokenize speech for "+speaker+": " + str(all_speeches)

        # save congressmen's speaker stats to csv and pickle, and n-grams to pickle
        with open(CONGRESSMENSTATSCSVFILE,'w') as csvfile:
            writer = csv.DictWriter(csvfile, 
                fieldnames=['congressman','speeches','sentences','words','gradeLevel'])
            writer.writeheader()
            writer.writerows(speaker_stats.values())
        savePickle(CONGRESSMENSTATSFILE, speaker_stats)    
        savePickle(CONGRESSMENNGRAMFILE, speaker_ngrams)
        print '  Total sentences and words considered: ' + str(SENTENCE_COUNT) +", "+ str(WORD_COUNT)
    
    speeches = None
    
    all_ngrams = not REBUILD_DATA and loadPickle(ALLCRNGRAMFILE)
    if not all_ngrams:
        REBUILD_DATA = True
        #combine n-grams into democratic and republican (and all) n-grams
        print "Aggregating n-grams by party of speaker..."
        dem_bigrams = defaultdict(int) # default to 0 if not found (int == lambda: 0)
        rep_bigrams = defaultdict(int)
        dem_trigrams = defaultdict(int)
        rep_trigrams = defaultdict(int)
        count = 0
        for (congressman,ngrams) in speaker_ngrams.viewitems():
            bigrams, trigrams = ngrams        
            congressmanParty=congressman[4]
            if (congressmanParty=='Democrat'):
                mergeHashes(dem_bigrams,bigrams)
                mergeHashes(dem_trigrams,trigrams)
                count+=1
            elif (congressmanParty=='Republican'):
                mergeHashes(rep_bigrams,bigrams)
                mergeHashes(rep_trigrams,trigrams)
                count+=1
            else:
                print '  Ignoring party "'+congressmanParty+'" for congressman of '+ congressman[2]
                #continue # exclude phrases uttered only by nonpartisans
        print "  - Included n-grams from "+str(count)+" congressmen." 

        # Exclude certain n-grams: leadership names and state names
        for bigram in omitted_bigrams:
            dem_bigrams.pop(bigram, None) # remove from dict (return None if doesn't exist)
            rep_bigrams.pop(bigram, None)
        ((bigrams, trigrams), __) = tokenize(omitted_phrases)
        for bigram in bigrams.keys():
            dem_bigrams.pop(bigram, None)
            rep_bigrams.pop(bigram, None)
        for trigram in trigrams.keys():
            dem_trigrams.pop(trigram, None)
            rep_trigrams.pop(trigram, None)

        all_ngrams = (dem_bigrams, rep_bigrams, dem_trigrams, rep_trigrams)
        savePickle(ALLCRNGRAMFILE,all_ngrams)

    (dem_bigrams, rep_bigrams, dem_trigrams, rep_trigrams) = all_ngrams
    
    # Combine into list of all n-grams (regardless of party)
    all_bigrams = dem_bigrams
    all_trigrams = dem_trigrams
    mergeHashes(all_bigrams,rep_bigrams)
    mergeHashes(all_trigrams,rep_trigrams)
    
    print 'Bi-gram samples (least and most used):'        
    bg = sorted(all_bigrams.viewitems(), key=itemgetter(1)) # sort on counts
    print bg[0:3000]
    print bg[-3000:]
    
    # print counts 
    print 'found unique and total bigrams:'
    print len(all_bigrams) # unique
    print sum([count for count in all_bigrams.values()]) # total number
    print 'and found unique and total trigrams:'
    print len(all_trigrams) # unique
    print sum([count for count in all_trigrams.values()]) # total number

    print 'CR Parsing complete.'

if __name__ == "__main__":
    main(sys.argv)