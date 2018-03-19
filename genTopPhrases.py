# -*- coding: utf-8 -*-
"""
Created on Sat May  3 01:20:29 2014

@author: briggsjt

Choose n-grams to be used for analysis.
Can be run for a single month, a single year, or multiple years (at once)

Inputs: All-station N-grams file (from CC data),
    All-congress n-grams file (from CR data),
    N-gram chisq file (from partisan usage in CR data)
Output: Top n-grams file with TOTAL_NGRAMS of each type to be used for analysis
Intermediates: All station n-grams file (which combines all stations)
    Candidate n-grams file with n-grams appearing multiple times in the CR and 
        between Min & Max count times in the CCs
"""

import os, sys, gc
#from os import walk
from operator import itemgetter
from collections import defaultdict
import fractions

from common import loadPickle, savePickle, CCpath, ngramname, regularizeDate, \
                    STATIONNGRAMFILE, NGRAMCHISQFILE, ALLCRNGRAMFILE, TOPNGRAMSFILE

# flag to ignore any pickle files and regenerate data from scratch
REBUILD_DATA = False

MIN_CR_NGRAM_COUNTS = [[10, 5], [20, 10]] # for bi, tri-grams, single month/year and multi-years
# min & max for bigrams & trigrams, for single-month, single-year, and per year for multi-year respectively
MIN_NGRAM_COUNTS= [[265, 50],    [700, 190],  [150, 40]  ]
MAX_NGRAM_COUNTS= [[4200, 4200], [6500,5000], [3200,1500]]
TOTAL_NGRAMS = [[500, 400], [1000, 800]] # for bigrams and trigrams, for single-month and year(s) respectively

ALLSTATIONNGRAMSFILE = 'allstation.json.bz2'
CANDIDATENGRAMSFILE = 'candidates.pickle'

def mergeHashes(destHash,otherHash):
    """Like the common mergeHashes, except we stringify ngram tuples"""
    for (ngram,othercount) in otherHash.viewitems():
        # convert tuple to string to aid later serialization:
        # (otherwise json won't support it and conversion wastes a lot of space we don't have)
        if isinstance(ngram, tuple):
            ngram = ','.join(ngram) 
        destHash[ngram] += othercount

def chisq(freqDem, freqDemOther, freqRep, freqRepOther, C = 0):
    """Calculate a chi-squared test statistic (score) from the usage frequencies of a phrase, C is a smoothing constant"""
    freqDem += C
    freqRep += C    
    numerator = long(freqRep*freqDemOther - freqDem*freqRepOther)
    numerator = numerator * numerator
    denominator = long((freqRep + freqDem) * (freqRep + freqRepOther) * \
        (freqDem + freqDemOther) * (freqRepOther + freqDemOther))
    if denominator ==0:
        print 'wtf!'
    return float(fractions.Fraction(numerator,denominator))

def combineCCNgrams(n, years, input_prefixes):
    """Merge n-gram counts across all the stations, months and years"""
    print "Loading and merging pre-generated station n-gram files..."        
    ## first, combine station ngrams into one, from all monthly station-ngram files
    all_station_ngrams = defaultdict(int)
    fns = []
    if len(input_prefixes)==1: # one or more years
        fns = [os.path.join(CCpath,yr+'{0:02d}'.format(mon)+'_'+STATIONNGRAMFILE) \
                  for yr in years for mon in range(1,13)]
    else: # a single month (combining adjacent months)
        fns = [os.path.join(CCpath,prefix+'_'+STATIONNGRAMFILE) for prefix in input_prefixes]
    for f in fns:
        print 'Loading ' + ngramname(n) + ' from ' + f + '...'
        station_ngrams = loadPickle(f)
        if not station_ngrams: print "ERROR loading " + f
        ngrams = defaultdict(int)
        for this_station_ngrams in station_ngrams.viewvalues():
            mergeHashes(ngrams, this_station_ngrams[n])
        station_ngrams = None
        print "  dropping station n-grams used only once this period"
        singles = [key for (key,value) in ngrams.viewitems() if value <= 1]
        for key in singles:
            del ngrams[key]
        mergeHashes(all_station_ngrams, ngrams)
        ngrams = None
#    the_counts = all_station_ngrams.viewvalues()
#    the_counts_aboveone = [x for x in the_counts if x>1]
#    print str(len(the_counts_aboveone)) + " out of " + str(len(the_counts)) + " CC bigrams have count>1"
    return all_station_ngrams
    
def getCandidateNgrams(n,all_cr_ngrams,all_station_ngrams,MIN_CR_COUNT,MIN_COUNT,MAX_COUNT):
    """Find n-grams appearing >1x in the CR and having between MIN and MAX counts in CCs"""
    print "Finding candidate n-grams..."    
    i=0
    candidate_ngrams = set()
    for (ngram,count) in all_cr_ngrams.viewitems():
        if count>=MIN_CR_COUNT: # drop anything with too few CR usages
            i+=1
            # key stored as single string in this dict:
            ngramstr = ','.join(ngram) if isinstance(ngram, tuple) else ngram
            cc_count = all_station_ngrams.get(ngramstr, 0) 
            if cc_count >= MIN_COUNT[n] and cc_count <= MAX_COUNT[n] and cc_count > count*1.5:
                candidate_ngrams.add(ngram)
                print "added candidate with cc_count "+str(cc_count)+", cr_count "+str(count)+": "+ ngram
            else:
                if cc_count+MIN_COUNT[n]/3>=MIN_COUNT[n] and cc_count-MAX_COUNT[n]/5<=MAX_COUNT[n]:
                    if cc_count <= count*1.5 and cc_count >= count*1.25: #borderline procedural
                        print "rejected procedural cc_count "+str(cc_count)+", cr_count "+str(count)+": " + ngram
                    else:
                        print "rejected borderline cc_count "+str(cc_count)+", cr_count "+str(count)+": " + ngram
#                elif cc_count==0:
#                    print "ngram with 0 CC count: " + ngram
    print "\n\n\n#/candidate "+ngramname(n)+" = " + str(len(candidate_ngrams))
    print "out of " + str(i) + " CR "+ngramname(n)+" w/ count>"+str(MIN_CR_COUNT)
    return candidate_ngrams

def getFinalNgrams(candidate_ngrams,ngram_chisqs,total_ngrams):
    """Find total_ngrams n-grams having highest chi-sq among candidates"""
    print "Finding top chisq n-grams from candidates..."
    top_ngrams = []
    dem_ngrams = []
    rep_ngrams = []
    for ngram_chisq in ngram_chisqs: #(these are in reverse-sorted order)
        (ngram,chisq,demcount,repcount) = ngram_chisq
        if (ngram in candidate_ngrams):
            print ngram_chisq
            top_ngrams.append( ngram_chisq )
            if demcount<repcount:
                rep_ngrams.append( ngram )
            else:
                dem_ngrams.append( ngram )
            if len(top_ngrams) >= total_ngrams: break

    print '\nReps'    
    print rep_ngrams
    print "\nDems"
    print dem_ngrams
#    print len(rep_ngrams)
#    print len(dem_ngrams)
    if len(top_ngrams)<total_ngrams: 
        print "WARNING!!! Not enough n-grams: "+str(len(top_ngrams))+"!!"
    return top_ngrams

def main(args):
    global years, REBUILD_DATA
    
    years = []
    month = None # unset month ==> combine all provided years. year and month provided ==> process just that month
    if len(args) < 2:
        print 'no year(s) passed in as parameter! Exiting.'
        exit()
    else:        
        # allow specifying multiple (consecutive) years; first arg is script name
        for i in range(1, len(args)):
            if (i==2 and int(args[i])<1800):
                # will run for single month
                month = args[i] # should be provided as 2-digit month, eg '03'
            else:
                # will run for multiple years as one run
                years.append(args[i])
            
                
    input_prefixes = []
    output_prefix = ""
    if month: 
        year = years[0]
        # for single month analyses, use the 4 months begining 2 months before the month in question
        output_prefix = year + month # eg 201308
        print "Running in single-month mode for " + output_prefix
        input_prefixes.append(regularizeDate(int(year), int(month)-2))
        input_prefixes.append(regularizeDate(int(year), int(month)-1))
        input_prefixes.append(regularizeDate(int(year), int(month)))
        input_prefixes.append(regularizeDate(int(year), int(month)+1))
        MIN_NGRAM_COUNT = MIN_NGRAM_COUNTS[0]
        MAX_NGRAM_COUNT = MAX_NGRAM_COUNTS[0]
        MIN_CR_NGRAM_COUNT = MIN_CR_NGRAM_COUNTS[0]
    elif len(years)>1:
        output_prefix = years[0] + '-' + years[-1][-1:] # last year take (only) 1 digit eg 2013-4
        input_prefixes = [output_prefix]
        print "Running in multi-year mode for " + output_prefix
        MIN_NGRAM_COUNT = MIN_NGRAM_COUNTS[2]
        MAX_NGRAM_COUNT = MAX_NGRAM_COUNTS[2]
        MIN_NGRAM_COUNT[0] *= len(years)
        MIN_NGRAM_COUNT[1] *= len(years)
        MAX_NGRAM_COUNT[0] *= len(years)
        MAX_NGRAM_COUNT[1] *= len(years)
        MIN_CR_NGRAM_COUNT = MIN_CR_NGRAM_COUNTS[1]
    else:
        output_prefix = years[0]
        input_prefixes = [output_prefix]
        print "Running in single-year mode for " + output_prefix
        MIN_NGRAM_COUNT = MIN_NGRAM_COUNTS[1]
        MAX_NGRAM_COUNT = MAX_NGRAM_COUNTS[1]
        MIN_CR_NGRAM_COUNT = MIN_CR_NGRAM_COUNTS[0]

    print "Allowing Ngrams with CC_COUNT between "+str(MIN_NGRAM_COUNT)+" and "+str(MAX_NGRAM_COUNT)

    # for bigrams and trigrams:
    for n in range(2):
        print "---- PROCESSING "+ngramname(n)+" ----"

        ## Load /join congress n-grams
        print "Loading pre-generated congress n-gram files..."
        alldem_cr_ngrams = defaultdict(int)
        allrep_cr_ngrams = defaultdict(int)
        for prefix in input_prefixes:
            fn = os.path.join('CR',prefix+ALLCRNGRAMFILE)
            cr_ngrams = loadPickle(fn)
            if not cr_ngrams:
                print 'ERROR: Unable to find necessary ngram pickle. ' + fn         
                return
            mergeHashes(alldem_cr_ngrams, cr_ngrams[n*2+0])
            mergeHashes(allrep_cr_ngrams, cr_ngrams[n*2+1])
            
        # Recombine into list of all n-grams (regardless of party)
        all_cr_ngrams = alldem_cr_ngrams.copy()
        mergeHashes(all_cr_ngrams, allrep_cr_ngrams)
        print 'done' 
   
        ## based (only) upon CR usage, calculate chisq of usages
        chisqFn = os.path.join('CR',output_prefix+ngramname(n)+'_'+NGRAMCHISQFILE)
        ngram_chisqs = not REBUILD_DATA and loadPickle(chisqFn)
        if not ngram_chisqs:
            REBUILD_DATA = True
            # calculate chisq for each n-gram
            ngram_chisqs = []
            numdemphrases = long(sum(list(alldem_cr_ngrams.viewvalues())))
            numrepphrases = long(sum(list(allrep_cr_ngrams.viewvalues())))
            print "Calculating ChiSq stats for "+str(numdemphrases)+","+str(numrepphrases)+" dem, rep phrases..."
            for ngram in all_cr_ngrams.viewkeys():
                demcount = alldem_cr_ngrams.get(ngram,0)
                otherdemcount = numdemphrases - demcount
                repcount = allrep_cr_ngrams.get(ngram,0)
                otherrepcount = numrepphrases - repcount
                assert demcount>0 or repcount>0
                csq = chisq(demcount,otherdemcount,repcount,otherrepcount, 2) # Bayesian smoothing
                ngram_chisqs.append((ngram,csq,demcount,repcount))
            print "done. Sorting and saving."    
            ngram_chisqs.sort(key=itemgetter(1), reverse=True)
            savePickle(chisqFn, ngram_chisqs)
        else:
            print 'Loaded pre-calculated chisq measures'
        alldem_cr_ngrams = None;  allrep_cr_ngrams = None
       
        ## Load / join station n-grams
        print "loading or generating combined-station ngram file"
        allstationngramFn = output_prefix+ngramname(n)+'_'+ALLSTATIONNGRAMSFILE
        all_station_ngrams = not REBUILD_DATA and \
                                loadPickle(allstationngramFn)            
        if not all_station_ngrams:
            all_station_ngrams = combineCCNgrams(n, years, input_prefixes)
            print "Saving all station n-grams to disk..."
            savePickle(allstationngramFn, all_station_ngrams)
        
        ## Find candidate n-grams
        candidatengramsFn = output_prefix+ngramname(n)+'_'+CANDIDATENGRAMSFILE
        candidate_ngrams = not REBUILD_DATA and loadPickle(candidatengramsFn)
        if not candidate_ngrams:    
            candidate_ngrams = getCandidateNgrams(n,all_cr_ngrams,all_station_ngrams,
                                                  MIN_CR_NGRAM_COUNT[n],
                                                  MIN_NGRAM_COUNT,MAX_NGRAM_COUNT)
            savePickle(candidatengramsFn, candidate_ngrams)
            
        all_station_ngrams = None
        all_cr_ngrams = None
    
        ## Find top n-grams
        topngramsFn = output_prefix+ngramname(n)+'_'+TOPNGRAMSFILE
        top_ngrams = not REBUILD_DATA and loadPickle(topngramsFn)
        if not top_ngrams:    
            top_ngrams = getFinalNgrams(candidate_ngrams, ngram_chisqs, \
                            TOTAL_NGRAMS[0][n] if month else TOTAL_NGRAMS[1][n])
            savePickle(topngramsFn, top_ngrams)
            
        candidate_ngrams = None; top_ngrams = None
        gc.collect()


if __name__ == "__main__":
    main(sys.argv)