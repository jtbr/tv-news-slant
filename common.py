# -*- coding: utf-8 -*-
"""
Created on Wed Aug 17 16:17:24 2016

Common functions and data for News project

@author: Justin
"""
try:
    import cPickle as pickle
except:
    import pickle
import ujson as json
from bz2 import BZ2File

from fox_1990_stoplist import fox_stoplist

ghentzkow_shapiro_stoplist_additions=['monday','tuesday','wednesday','thursday',
    'friday','saturday','sunday', 'hart','dirksen','senate','house','office','building']
my_stoplist_additions=['caucus','speaker','committee','member','senator',
    'committees','colleague','colleagues','chairman','na',"n't",'am','thank','thanks','time']
stopwords = set(fox_stoplist + ghentzkow_shapiro_stoplist_additions + my_stoplist_additions)

# eliminate n-grams ...
# consisting only of their names/titles:
leadership = "Mr. President Barack Obama President Obama. Mr. Obama. Vice President Biden Vice President Joe Biden. Mr. Biden. Mr. Boehner. Minority Leader John Boehner Minority Leader Boehner. Mrs. Pelosi. Minority Leader Nancy Pelosi Minority Leader Pelosi. Majority Leader Harry Reid Majority Leader Reid. Mr. Reid. Majority Leader Mitch McConnell Majority Leader McConnell. Mr. McConnell. Minority Leader Mitch McConnell Minority Leader McConnell. Paul Ryan. Mr. Ryan. " #"speaker" is a stopword
# of often used congressional phrases: - normally handled by CC_COUNT>CR_COUNT condition (but not always)
omitted_phrases = "ask unanimous consent. yield balance of time. can't yield minute. won't yield floor. yield time. reserve balance. yeas and nays. bill pass bill piece legislation pass legislation. offer bill oppose bill support bill author bill provide bill offer amendment support amendment oppose amendment author amendment provide amendment offer act support act oppose act author act provide act. vice chair." 
omitted_phrases += leadership

# eliminate bigrams ...
# that are simply state names ('new' is a stopword...)
state_bigrams = [('district','columbia'), ('north','carolina'), ('north', 'dakota'), ('rhode', 'island'), ('south', 'carolina'), ('south', 'dakota'), ('west','virginia'), ('york','jersey')]
# that are alliterations of numbers
number_bigrams = [('hundr', 'thousand'), ('ten','thousand'), ('hundr', 'million'), ('ten', 'million'), ('hundr','billion'), ('ten','billion'), ('million','billion')]
# that are clearly not partisan but may appear so
omitted_bigrams = [('ladi', 'gentlemen'), ('web', 'site'), ('speak','minut'), ('morn','busi'), ('democrat','bill'), ('republican', 'bill'), ('democrat','amend'), ('republican','amend'), ('democrat','legisl'), ('republican','legisl'), ('democrat','budget'), ('republican', 'budget'), ('republican','friend'), ('democrat','friend'), ('republican','leadership'), ('democrat','leadership'), ('republican', 'major'), ('democrat','major'), ('republican','party'), ('democrat','party'), ('democrat','republican'), ('republican','democrat')]
omitted_bigrams += state_bigrams + number_bigrams


CCpath = 'CCs/stationngrams' # path to stationngrams
STATIONNGRAMFILE = 'stationngrams.pickle.bz2' # 2015-12_ prefixed - ngrams for CCs in CCpath
CONGRESSMENNGRAMFILE = 'congressmenngrams.pickle' # year prefixed - ngrams by congressman
CONGRESSMENSTATSFILE = 'congressmenstats.pickle' # year prefixed - stats @ congressmen's speeches
ALLCRNGRAMFILE = 'allcrngrams.pickle' # year/yearmo prefixed - ngrams for dems/republicans (combine for "all")
NGRAMCHISQFILE = 'ngramchisq.pickle' # year/yearmo prefixed - chisqs for n-grams
TOPNGRAMSFILE = 'top.pickle' # year/yearmo and ngramname prefixed - final analysis n-grams


def ngramname(n):
    """Return the name of the nth n-gram"""
    ngrams = ['bigrams', 'trigrams']
    return ngrams[n]

def addNgrams(thehash,ngrams):
    """Add a list of ngrams (as tuples) to the n-gram-count hash"""
    for ngram in ngrams:
        thehash[ngram] += 1
        #count = thehash.get(ngram,0) # method using standard dict
        #thehash[ngram] = count + 1

def mergeHashes(destHash,otherHash):
    """Merge count maps, adding otherHash into destHash"""
    for (ngram,othercount) in otherHash.viewitems():
        destHash[ngram] += othercount
        #count = destHash.get(ngram,0) #method using std dict
        #destHash[ngram] = count + othercount
        
def loadPickle(filename):
    """Load and return data contained in a pickle file or json file, possibly bz2 compressed"""
    try:
        if filename.endswith('.bz2'):
            f=BZ2File(filename,mode='r')
        else:
            f = open(filename,'r')
        if filename.find('json')>=0:
            data = json.load(f)
        else:
            data = pickle.load(f)
        f.close()
    except:
        data = None
    return data

def savePickle(filename, data):
    """Save data into the named pickle or json file, possibly bz2 compressed"""
    if filename.endswith('.bz2'):
        f = BZ2File(filename,mode='wb')
    else:
        f = open(filename, 'wb')
    if filename.find('json')>=0:
        json.dump(data,f)
    else:
        pickle.dump(data, f)
    f.close()
    
def regularizeDate(yr, mon):
    '''take integer year,month with month in [-11,23] and return datestr yyyymm so month in [1,12]'''
    if (mon >= 1 and mon <= 12):
        return str(yr)+'{0:02d}'.format(mon)
    elif (mon < 1):
        return str(yr-1)+'{0:02d}'.format(mon+12)
    else: #mon>12
        return str(yr+1)+'{0:02d}'.format(mon-12)
            
