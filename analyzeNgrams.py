# -*- coding: utf-8 -*-
"""
Created on Thu Apr 24 18:40:28 2014

@author: Justin

Analyzes n-grams from CR and broadcast TV CCs - 

Uses any of 5 different measures of congressional ideology and 
generates phrase hues for top/final n-grams, slant estimates for congressmen,
and slant estimates for stations, either as a single SUMMARY estimate for the 
whole period, on a MONTHLY basis using a single set of n-grams for the whole 
period, or on a MONTHLY_NGRAMS basis with n-grams varying over the period

Inputs: Top (analysis n-grams) list file,
    each congressman's n-grams file,
    each congressman's speech statistics file,
    congressional ideology file for specified type

Intermediate file: Regression inputs file
    (for summary), Station final n-grams file
    
Outputs: Congressmen ideologies (slants) (actual and implied) csv file
    Station slants csv file
    Station slants SE csv file
    Station slants pickle file (containing the CSV contents with more details)

Note: to run with merged results, first merge n-grams using ipython notebook top_ngrams. 
    Then add 'monthlymerged.' to the end of REG_TYPE, and '_monthlymerged_' after the 
    input_prefix in top-ngram file name in doAnalysis(). Then run with SUMMARY.

"""

import os, sys, csv, math
import numpy as np
from numpy import array
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import OLSInfluence
from collections import defaultdict
from operator import itemgetter

from common import loadPickle, savePickle, mergeHashes, TOPNGRAMSFILE, CONGRESSMENNGRAMFILE, \
                CONGRESSMENSTATSFILE, STATIONNGRAMFILE, CCpath, ngramname, regularizeDate

#--- PARAMS ---
# flag to ignore any RegressionInputs (and finalstationngrams) pickle files and regenerate data from scratch
REBUILD_DATA = True
#IDEOLOGY TYPES: 'elec2004' 'elec2008' 'pvi2010' 'dwnom' 'ada' 
IDEOLOGY_TYPE = 'dwnom' 
# note: may need to confirm proper functioning of first 3 types for SUMMARY (are scores averaged, eg?)
#--------------

STATIONSLANTSPRE = 'stationslants'
REG_TYPE = '.WLSRob.' # regression type performed (WLS w/ robust se's)
            
def compileFinalNgramCounts(final_ngrams,compiled_final_station_ngrams,station_ngrams):
    """Join the final_ngrams in station_ngrams to compiled_final_station_ngrams"""
    for (station, ngrams) in station_ngrams.viewitems():
        thisstation_finalngrams = \
            compiled_final_station_ngrams.get(station,(defaultdict(int),))
        for i in range(len(final_ngrams)): # bigrams, trigrams, ...
            if len(thisstation_finalngrams)<=i: # 1st time this station has been used- add a dict
                thisstation_finalngrams = thisstation_finalngrams + (defaultdict(int), )
            final_igrams = final_ngrams[i]
            for igram in final_igrams: # eg, each bigram in final_bigrams
                count = ngrams[i].get(igram,0) # count of ngram usage on station
                thisstation_finalngrams[i][igram] += count

        compiled_final_station_ngrams[station] = thisstation_finalngrams
    return compiled_final_station_ngrams

def congressID(name, party, stateAbbr):
    """Return the congressman as 'Gephardt (D-MO)'"""
    partyAbbr = 'I'
    if (party=='Republican'): partyAbbr = 'R'
    elif (party=='Democrat'): partyAbbr = 'D'
    
    return name + ' (' + partyAbbr + '-' + stateAbbr + ')'


def findStationSlants(final_ngrams, intercepts, phrase_hues, phrase_hue_wts, station_ngrams):
    """Find the slants of the stations"""    
    ## find relative frequency of n-gram usage for each TV station
#    (final_bigrams, final_trigrams) = top_ngrams
    print 'Calculating relative frequencies of broadcaster\'s uses of slanted phrases...'

    #combine all igrams into a list (analysis phrases) (may differ from diagnostic phrases if congressmen ideologies were missing)
    phrases = [] 
    for final_igrams in final_ngrams:
        phrases += final_igrams
    
    station_pickledata = {}
    
    stations = []
    station_freqs = [] # list of lists
    station_totalcounts = []
    for (station, ngrams) in station_ngrams.viewitems():
        if station not in all_stations:
            print 'Skipping excluded station: ' + station
            continue
        # (bigram_count, trigram_count) = ngrams  # for station
        ngram_freqs = [];
        total_count = 0;
        for i in range(len(final_ngrams)):
            final_igrams = final_ngrams[i]
            for igram in final_igrams: # eg, each bigram in final_bigrams
                count = ngrams[i].get(igram,0) # count of ngram usage on station
                ngram_freqs.append( count )
                total_count+=count
        if total_count < 100:
            print 'Warning: fewer than 100 diagnostic phrases for station: ' + station + '!'
            if total_count < 25:
                print ' - Only ' + str(total_count) + ' SKIPPING!'
                continue
        else:
             print "Station "+station+" has "+str(total_count)+" diagnostic phrase usages."
        ngram_freqs = [ngram_freq / float(total_count) for ngram_freq in ngram_freqs]
        stations.append( station )
        station_freqs.append( ngram_freqs )
        station_totalcounts.append( total_count )
    station_freqs = array(station_freqs)
    
    intercepts = array(intercepts)
    x = array(phrase_hues)

    ## find severe outliers, mostly owing to a station's content eg, "public, radio" or "market, share"
    outlier_idxs = []
    for i in range(station_freqs.shape[0]): # size of first dimension, #/stations
        y = station_freqs[i,:] - intercepts
        mod_ols = sm.OLS(y, x)
        res_ols = mod_ols.fit(cov_type='HC1')
        oi = OLSInfluence(res_ols)
        outlier_idxs += np.where(oi.resid_studentized_internal>15.0)[0].tolist()
        
    ## drop outliers from regressions but leave in station_pickledata
    outlier_idxs = np.unique(outlier_idxs)
    if len(outlier_idxs)>0:
        print "\nremoving outliers: "+str(np.array(phrases)[outlier_idxs])+"\n at indices: "+str(outlier_idxs)
        x = np.delete(x, outlier_idxs)
        phrase_hue_wts = np.delete(phrase_hue_wts, outlier_idxs)

    ## regress stations' adjusted relative phrase frequencies on phrase-slant 
    ## indicators (slopes from last reg)
    station_slants = []
    station_slant_stderrs = []
    for i in range(station_freqs.shape[0]): # size of first dimension, #/stations
        y = station_freqs[i,:] - intercepts
        y = np.delete(y, outlier_idxs)
        
        station = stations[i]        
        mod_wls = sm.WLS(y,x, weights=phrase_hue_wts)
        res_wls = mod_wls.fit(cov_type='HC1')
        print '\n' + station + ':\n'
        print res_wls.summary()
        slope = res_wls.params[0]
        rob_std_err = res_wls.HC1_se[0]
        station_slants.append(slope)
        station_slant_stderrs.append(rob_std_err)

        #save data in dict for pickle; format: (station,slant,slant_stderr,ngram_totalcount,ngram_freqs)
        station_pickledata[station] = \
            (station,slope,rob_std_err,station_totalcounts[i],station_freqs[i,:],outlier_idxs)
    
    print station_ngrams.viewkeys()
    print station_slants
    assert len(station_slants) == len(stations) == len(station_slant_stderrs)
    return (stations, station_slants, station_slant_stderrs, station_pickledata)

# stations to include in report (and order of them):
all_stations = ['ABC', 'NBC', 'CBS', 'PBS', 'CNN', 'FOXNEWS', 'MSNBC', 
                'CNBC', 'FBC', 'BLOOMBERG', 'NPR', 'ALJAZAM', 'BBC']# 'COM', 'LINKTV']

def congressNum(year):
    # starting from the 83rd congress in 1953-1954, sessions were only in 2 calendar years
    return int((year - 1953)/2) + 83


def readIdeologies(ideologyType, years):
    """Reads in some measure of ideology for congressmen or their districts
    
    Valid ideologyTypes are 'elec2004' 'elec2008' 'pvi2010' 'dwnom' 'ada' 'adamean'
    """
    ideology = {} 
    csvFilename = ""
    if ideologyType.startswith("elec"):
        year = ideologyType[-4:]
        csvFilename = "ideologies/MasterElections2004-08.csv"
        print 'Loading '+year+' presidential election results as measure ' \
                + 'of congressional ideology...'
        with open(csvFilename, 'rb') as csvfile:
            electionResults = csv.DictReader(csvfile)
            for district in electionResults:
                if district['Year']==year:
                    state = district['State'] #state abbreviation actually
                    district_num = int(district['District'])
                    if district_num==0: # it's the senate, n/a
                        district_type = "senate"                        
                    else:
                        district_year = int(district['District Year'])
                        if district_year <= 2010:
                            district_type = "pre2012"
                            # in 2012, districts from 2010 census took effect
                        else:
                            district_type = "post2012"
                    #margin = float(district['M%'])
                    #if district['Winner'] == 'Kerry':
                    #    margin = -margin
                    #ideology[(state,district_num)] = margin/100.0
                    #actually, the paper uses Bush vote share, not margins:
                    repVoteShare = float(district['Rep%']) / 100.0
                    ideology[(state,district_num,district_type)] = repVoteShare
    
    elif ideologyType=="pvi2010":
        csvFilename = "ideologies/MasterPVI_2010.csv"
        print 'Loading 2010 partisan voting index (based upon 2004 & 2008 ' \
                + 'elections) as measure of congressional ideology...'
        with open(csvFilename, 'rb') as csvfile:
            pvis = csv.DictReader(csvfile)
            for district in pvis:
                state = district['State'] #state abbreviation actually
                district_num = int(district['District'])
                if district_num==0: # it's the senate, n/a
                    district_type = "senate"                        
                else:
                    district_year = int(district['District Year'])
                    if district_year <= 2010:
                        district_type = "pre2012"
                        # in 2012, districts from 2010 census took effect
                    else:
                        district_type = "post2012"

                pvi = float(district['2010 pvi'])
                ideology[(state,district_num,district_type)] = pvi
    
    elif ideologyType=="dwnom":
        csvFilename = "ideologies/DWNOM_111-114.csv"
        print 'Loading DW Nominate scores as measure of congressional ideology...'
        with open(csvFilename, 'rb') as csvfile:
            dwnomscores = csv.DictReader(csvfile)
            for congressman in dwnomscores:
                #state = congressman['stateabbr']
                icpsr = int(congressman['icpsr'])
                #district_num = int(congressman['district'])
                session = int(congressman['session'])

                dwnom = float(congressman['dwnom_1']) # use the first dimension only
                ideology[(icpsr, session)] = dwnom

    elif ideologyType.startswith("ada"):
        csvFilename = "ideologies/2009-15_adascores.csv"
        print 'Loading Americans for Democratic Action (ADA) scores as '  \
                + 'measure of congressional ideology...'
        with open(csvFilename, 'rb') as csvfile:
            dwnomscores = csv.DictReader(csvfile)
            for congressman in dwnomscores:
                cong_year = int(congressman['year'])
                session = congressNum(cong_year)
                #state = congressman['stateabbr']
                icpsr = int(congressman['icpsr'])
                #district_num = int(congressman['district'])
                key = (icpsr, session)
                
                if ideologyType.endswith("mean"):
                    # use the member's mean score across his tenure
                    score = congressman['adjusted.member.mean.ada']
                else:
                    #use the score for the given year
                    score = congressman['adjusted.ada']
                
                #unlike other measures, ada has more dem as higher; reverse this.
                ada = 100.0 - float(score) # some scores <0 or >100, that's ok
                try:
                    # Average over the years in a session seperate
                    otheryear_ada = ideology[key]
                    ideology[key] = 0.5 * (otheryear_ada + ada)
                except:
                    ideology[key] = ada
    
    return ideology

#TODO: remove this brute force search. Instead have congressmen ngram and stats hashes use ICPSR as key 
# (in parseCR and here) and make a new hash (in read_icpsr*.py) to lookup name etc based upon icpsr
def findRecord(icpsr_id, congressmen_dict):
    '''find the record with the given icpsr_id and return it as a (key, value) tuple'''
    for (congressman, value) in congressmen_dict.items():
        (ICPSRMemberID, StateAbbr, StateName, DistrictNum, PoliticalParty, Name) = congressman
        if (icpsr_id == ICPSRMemberID): # stays the same across sessions/ district numbers
            return value
    return None
    

def getPrefix(prefix, offset):
    ''' take prefix in form yyyymm and return same form, offset months away'''
    yr = prefix[0:4]
    mon = prefix[4:]
    
    return regularizeDate(int(yr),int(mon)+offset)    


def combineCongressNgrams(reference, adjacent):
    '''Combine the entries from new into reference CongressNgrams'''
    for (congressman, new_ngrams) in adjacent.viewitems():
        (ICPSRMemberID, StateAbbr, StateName, DistrictNum, PoliticalParty, Name) = congressman

        # note: this brute force search is used rather than a lookup, in order to allow merging 
        # across sessions in which districts/parties may change
        ref_ngrams = findRecord(ICPSRMemberID, reference)
        if ref_ngrams:
            for i in range(len(new_ngrams)):
                mergeHashes(ref_ngrams[i], new_ngrams[i])
        else:
            reference[congressman] = new_ngrams
            print "congressman "+congressID(Name,PoliticalParty,StateAbbr)+" not found in current month. adding."


def doAnalysis(input_prefix, slantCsvWriter, slantSeCsvWriter, ANALYSIS_TYPE, years):
    '''Do complete analysis from finding phrase hues to computing slants for a station'''

    global TOPNGRAMSFILE, CONGRESSMENNGRAMFILE, CONGRESSMENSTATSFILE, STATIONNGRAMFILE, CCpath, IDEOLOGY_TYPE

    REGINPUTSFILEPRE = 'regression_inputs'
    CONGRESSMENIDEOLOGIESPRE = 'congressmenideologies'
    STATIONFINALNGRAMSFILE = input_prefix+'stationfinalngrams-SUMMARY.pickle' # only for summary analyses

    final_ngrams = []
    # for bigrams, trigrams
    for i in range(2): 
        top = loadPickle(input_prefix+ngramname(i)+'_'+TOPNGRAMSFILE)
        if not top:
            print "unable to find final n-grams!!\n"
            return

        # (top_igrams,chisq,demcount,repcount) = top
        # strip out the chisq,demcount,repcount and convert from string to tuple
        top_igrams = [tuple(igrams[0].split(',')) for igrams in top] 
        final_ngrams.append(top_igrams);
        top=None

    REGINPUTSFILE = input_prefix+REGINPUTSFILEPRE + '-' + IDEOLOGY_TYPE + '.pickle'
    reg_data = not REBUILD_DATA and loadPickle(REGINPUTSFILE)
    print ("Loaded input file " if reg_data else "Unable to load optional, cached ") + REGINPUTSFILE
    if not reg_data:  
        ## read in ideologies of the specified kind
        if ANALYSIS_TYPE=='SUMMARY':
            #modify IDEOLOGY_TYPE to use mean measures over at least the period to be summarized
            #TODO: could average relevant scores ourselves...
            if IDEOLOGY_TYPE=='ada':
                IDEOLOGY_TYPE = 'adamean'
        ideology = readIdeologies(IDEOLOGY_TYPE, years)
        if len(ideology) == 0:
            print "unable to load ideologies correctly"
            return
            
        ## find relative frequency of n-gram usage for each congressman and assign margins
        print 'Calculating relative frequencies of congressmen\'s uses of slanted phrases...'

        congressmen_freqs = [] # list of lists, #/congressmen using ngram and having ideologies x #/phrases
        congressmen_ideologies = [] # per congressman using ngrams and having an ideology
        congressmen_weights = []
        congressmen_totalcounts = []
        congressmen_tags = []
        
        ngramsfile = os.path.join('CR', input_prefix+CONGRESSMENNGRAMFILE)
        statsfile = os.path.join('CR', input_prefix+CONGRESSMENSTATSFILE)
        congressmen_ngrams = loadPickle(ngramsfile)
        congressmen_stats = loadPickle(statsfile)
        if (not congressmen_ngrams or not congressmen_stats):
            # in October 2014, congress was in session for a total of 29 seconds.
            # in Oct. 2012 it sat weekly only to adjourn itself and pledge allegiance
            # Process anyway using adjacent months
            print "WARNING: unable to load congressmen data for current month"
            if (congressmen_ngrams == None or congressmen_stats == None): #eg, not {}
                print "aborting."
                return
        
        # Load 4-month period (3 additional months) for n-grams hue evaluation
        stats_addl = []
        if ANALYSIS_TYPE == 'MONTHLY_NGRAMS':
            for offset in [-2, -1, 1]:
                prefix = getPrefix(input_prefix, offset)
                ngram_fn = os.path.join('CR', prefix+CONGRESSMENNGRAMFILE)
                stats_fn = os.path.join('CR', prefix+CONGRESSMENSTATSFILE)
                addl_ngrams = loadPickle(ngram_fn)
                addl_stats = loadPickle(stats_fn)
                if (not addl_ngrams or not addl_stats):
                    print "WARNING: Unable to load adjacent congressmen data for "+prefix
                    if (addl_ngrams == None or addl_stats == None): #eg, not {}
                        print "aborting."
                        return
                print "  loaded adjacent ngrams with "+str(len(addl_ngrams))+" congressmen: "+prefix
                combineCongressNgrams(congressmen_ngrams, addl_ngrams)
                stats_addl.append(addl_stats)
                addl_ngrams = None;  addl_stats = None;

        #US_avg_ideology = ideology[('US',0)]
        for (congressman, congressman_ngrams) in congressmen_ngrams.viewitems():
            (ICPSRMemberID, StateAbbr, StateName, DistrictNum, PoliticalParty, Name) = congressman

            ngram_freqs = [];   
            total_count = 0;
            for i in range(len(final_ngrams)): #first bigrams, then trigrams, ...
                final_igrams = final_ngrams[i]
                for igram in final_igrams: # eg, each bigram in final_bigrams
                    count = congressman_ngrams[i].get(igram, 0)

                    ngram_freqs.append( count )
                    total_count += count
                    #TODO: let total_count be of ALL n-grams? (also above in findSlant...) 
                    # - prob no - rates would be swamped by non diagnostic phrases..
            if not any(ngram_freqs):
                print "Congressman " + congressID(Name,PoliticalParty,StateAbbr) \
                        + " used no slanted bigrams or trigrams. Dropping."
                continue
            
            sessionNum = congressNum(int(years[0]))
            maxSessionNum = congressNum(int(years[-1]))
            
            # obtain matching ideology from outside source        
            if (IDEOLOGY_TYPE.startswith("ada") or IDEOLOGY_TYPE == "dwnom"):
                found = False
                while not found and sessionNum<=maxSessionNum:   # loop only needed for SUMMARY analysis
                    try:
                        idlgy = ideology[(ICPSRMemberID, sessionNum)]
                        found = True
                    except:
                        if ANALYSIS_TYPE=='MONTHLY_NGRAMS':  
                            # try adjacent session ideology (only if member is not in current session)
                            mon = int(input_prefix[4:])
                            offset = -1 if mon<=2 else 1 if mon==12 else 0
                            if offset:
                                try:
                                    idlgy = ideology[(ICPSRMemberID, sessionNum+offset)]
                                    found = True
                                except:
                                    found = False
                    sessionNum += 1
                if not found:
                    print "Congressman " + str(ICPSRMemberID) + ", " \
                        + congressID(Name,PoliticalParty,StateAbbr) + " - no ideology found! Dropping."
                    continue
            else:
                idlgy = ideology[(StateAbbr, DistrictNum, 'pre2012' if sessionNum<113 else 'post2012')]

            ngram_freqs = [ngram_freq / float(total_count) for ngram_freq in ngram_freqs]
            congressmen_freqs.append( ngram_freqs )
            congressmen_totalcounts.append( total_count )
            congressmen_tags.append(congressID(Name,PoliticalParty,StateAbbr))
            congressmen_ideologies.append( idlgy )

            # sum up the sentences spoken from the different months
            sentences = 0
            cong_stats = congressmen_stats.get(congressman, None)
            if cong_stats: # may not exist in the current month (only in adjacent ones)
                sentences += cong_stats['sentences']
            for more_stats in stats_addl: # adjacent months for MONTHLY_NGRAMS
                cong_stats = findRecord(ICPSRMemberID, more_stats)
                if cong_stats:
                    sentences += cong_stats['sentences']

            # use sqrt of #/sentences spoken as weights on congressmen's speech
            congressmen_weights.append( math.sqrt(sentences) )

        congressmen_freqs = array(congressmen_freqs)
        
        stats_addl = None
        congressmen_ngrams = None
        ideology = None
        
        print "Analysis to be conducted on "+str(len(congressmen_totalcounts))+" congressmen who used analysis phrases."
        
        ## for each phrase/n-gram, regress congressmen's phrase_frequencies on congressmen's 
        ## ideology to find implied slant (hue) of phrases
        phrases = [] 
        #combine all bi-, tri-, etc grams into a list (phrases)
        for final_igrams in final_ngrams:
            phrases += final_igrams

        # Remove phrases with insufficient number of uses (if 0 uses, regressions will fail)
        for i in reversed(range(np.shape(congressmen_freqs)[1])):
            # Note: number of phrase usages may be lower than in genTopPhrases if ideology of speaker
            # is not found -- which may cause regressions to fail if usages are too low
            phrase_usages = int(np.sum(np.multiply(congressmen_freqs[:,i], 
                                                   congressmen_totalcounts)))
            if (phrase_usages < 5):
                #failsafe for when we can't find ideology for speakers of rare phrases, drop the phrase
                print "NOTE: dropping phrase "+str(phrases[i])+" with insufficient #/uses."
                # drop from congressmen usages, final-igrams, and phrases list
                congressmen_freqs = np.delete(congressmen_freqs,i,1) # remove ith column
                for igrams in final_ngrams:
                    try:
                        igrams.remove(phrases[i])
                        break
                    except:
                        continue         
                del phrases[i]

        numphrases=len(phrases)
        phrase_hues = [] #one per numphrase
        phrase_hue_wts = [] # "
        intercepts = []
        x = sm.add_constant(congressmen_ideologies,prepend=False)
        for i in range(numphrases):
            y = congressmen_freqs[:,i]

            # Note: number of phrase usages may be lower than in genTopPhrases if ideology of speaker
            # is not found -- which may cause regressions to fail if usages are too low
            phrase_usages = int(np.sum(np.multiply(y, congressmen_totalcounts)))
                
            mod_wls = sm.WLS(y,x,weights=congressmen_weights)
            res_wls = mod_wls.fit(cov_type='HC1')
            #dir(res_wls)
            (slope, intercept) = res_wls.params;
            if slope == 0.0: #shouldn't happen
                print y
            
            #std_err = res_wls.bse[0] #2nd param is intercept stderr
            # use MacKinnon & White (1985) heteroskedasticity robust SE (White 1980 
            # adjusted for dof), same as stata ",robust" cmd:
            rob_std_err = res_wls.HC1_se[0]
            
            # Note: could use t-value as weight, but prefer SE which measures confidence in the slope and 
            # gives higher correlation
            slope_t_value = slope/rob_std_err # use as weight

            print "  "+str(phrases[i])+" used "+str(phrase_usages)+" times, slope="+"{:.6f}".format(slope)+\
                    ", t="+"{:.2f}".format(slope_t_value)+"; R2="+"{:.3f}".format(res_wls.rsquared)
                        
            #print res_wls.summary()

            phrase_hues.append(slope)
            phrase_hue_wts.append(abs(1/rob_std_err))
            intercepts.append(intercept)

        phrase_slant_inds = zip(phrases,phrase_hues)
        phrase_slant_inds = sorted(phrase_slant_inds,key=itemgetter(1))

        print 'most_dem'    
        print phrase_slant_inds[0:60]
        print 'least_dem'
        print phrase_slant_inds[-1:-61:-1]

        ## sanity check phrase hues by seeing how well they predict ideology (regess
        ## congressmen freqs on phrase hues)
        implied_congressmen_slants = []
        slant_stderrs = []
        x = array(phrase_hues)
        for i in range(len(congressmen_ideologies)):
            y = congressmen_freqs[i,:] - intercepts
            
            mod_wls = sm.WLS(y,x, weights=phrase_hue_wts)
            res_wls = mod_wls.fit(cov_type='HC1')
            #print res_wls.summary()
            slope = res_wls.params[0];
            rob_std_err = res_wls.HC1_se[0]
    
            implied_congressmen_slants.append(slope)
            slant_stderrs.append(rob_std_err)
    
        (corr,__) = stats.pearsonr(congressmen_ideologies,implied_congressmen_slants)
        print "Correlation between ideology and implied slants of congressmen: " + str(corr)

        # save individual congressmen slants actual and implied (can be used to re-calculate correlation)
        with open(input_prefix + CONGRESSMENIDEOLOGIESPRE + '.WLSRob.' + IDEOLOGY_TYPE + '.csv', 'w') as f:
            writer = csv.writer(f)
            writer.writerow(["congressman", "electoral ideology", 
                             "speech implied slant", "slant std.err."])
            rows = (congressmen_tags,congressmen_ideologies,implied_congressmen_slants,slant_stderrs)
            rows = np.matrix.transpose(array(rows))
            writer.writerows(rows)

        # save the data needed to repeat both regressions here
        reg_data = (congressmen_tags, congressmen_freqs, congressmen_totalcounts, 
                    congressmen_ideologies, congressmen_weights, phrases, 
                    phrase_hues, phrase_hue_wts, intercepts, corr)
        savePickle(REGINPUTSFILE,reg_data)

    (congressmen_tags, congressmen_freqs, congressmen_totalcounts, congressmen_ideologies, 
     congressmen_weights, phrases, phrase_hues, phrase_hue_wts, intercepts, ideology_correlation) = reg_data
    

    stationdata = {}    

    print 'Processing monthly CCs...'
    
    # Find slants of stations based upon phrase hues, on a monthly basis    
    if ANALYSIS_TYPE == 'MONTHLY':
        for yr in years:
            for mon in range(1,13):
                datestr=yr+'{0:02d}'.format(mon)
                fn = os.path.join(CCpath,datestr+"_"+STATIONNGRAMFILE)
                station_ngrams = loadPickle(fn)
                if not station_ngrams:
                    print "Error loading " + fn
                
                print 'Finding Slants for ' + datestr + '...'
                (stations,slants,slantses,station_pickledata) = \
                    findStationSlants(final_ngrams, intercepts, phrase_hues, 
                                      phrase_hue_wts, station_ngrams)
            
                csvdatestr = yr + '-' + '{0:02d}'.format(mon) + '-01'
                csvkeyvals = dict(zip(stations,slants));
                csvkeyvals['date'] = csvdatestr
                slantCsvWriter.writerow(csvkeyvals)
    
                csvkeyvals = dict(zip(stations,slantses));
                csvkeyvals['date'] = csvdatestr
                slantSeCsvWriter.writerow(csvkeyvals)
    
                stationdata[datestr] = station_pickledata
                
    # Find slants of stations based upon phrase hues, as a summary for the whole period
    elif ANALYSIS_TYPE == 'SUMMARY' or ANALYSIS_TYPE == 'MONTHLY_NGRAMS':        
        if ANALYSIS_TYPE == 'SUMMARY':        
            final_station_ngrams = not REBUILD_DATA and loadPickle(STATIONFINALNGRAMSFILE)
            if not final_station_ngrams: 
                print 'Compiling station n-grams for period '+input_prefix+' ...'
                compiled_final_station_ngrams = {}
                for yr in years:
                    for mon in range(1,13):
                        datestr=yr+'{0:02d}'.format(mon)
                        fn = os.path.join(CCpath,datestr+"_"+STATIONNGRAMFILE)
                        print 'Aggregating slants for ' + datestr + '...'
                        station_ngrams = loadPickle(fn)
                        if not station_ngrams:
                            print "Error loading " + fn
                            
                        final_station_ngrams = \
                            compileFinalNgramCounts(final_ngrams, compiled_final_station_ngrams, 
                                                    station_ngrams)
        
                print 'Saving summary station final_ngrams pickle.\n'
                savePickle(STATIONFINALNGRAMSFILE, final_station_ngrams)
        else:
            fn = os.path.join(CCpath,input_prefix+"_"+STATIONNGRAMFILE)
            final_station_ngrams = loadPickle(fn)
            if not final_station_ngrams:
                print "Error loading " + fn
                return
        
        print 'Finding slants for '+input_prefix+' ...'
        (stations,slants,slantses,stationdata) = \
            findStationSlants(final_ngrams, intercepts, phrase_hues, phrase_hue_wts, 
                              final_station_ngrams)
        
        csvdatestr = input_prefix[0:4] + '-' + input_prefix[4:] + '-01'
        csvkeyvals = dict(zip(stations,slants)); 
        csvkeyvals['date'] = csvdatestr
        slantCsvWriter.writerow(csvkeyvals)

        csvkeyvals = dict(zip(stations,slantses)); 
        csvkeyvals['date'] = csvdatestr
        slantSeCsvWriter.writerow(csvkeyvals)
        
    return stationdata


def main(args):
    years = []
    if len(args) < 3 or not (args[1] == 'MONTHLY' or args[1] == 'SUMMARY' or args[1] == 'MONTHLY_NGRAMS'):
        print 'usage: analyzeNgrams [analysis_type] <years>\n' + \
              '  where analysis_type SUMMARY provides a single estimate for all following years,\n' + \
              '  MONTHLY provides monthly estimates based upon a single set of n-grams & their single set of hues,\n' + \
              '  and MONTHLY_NGRAMS provides monthly estimates based upon monthly n-grams'
        exit()
    else:        
        # allow specifying multiple (consecutive) years; first arg is script name
        ANALYSIS_TYPE = args[1];
        for i in range(2, len(args)):
            # will run for multiple years as one run
            years.append(args[i])    
    
    year_prefix = years[0]
    if len(years)>1:
        year_prefix = years[0] + '-' + years[-1][-1:] # last year take (only) 1 digit eg 2013-4
        
    suffix = '-' + ANALYSIS_TYPE + REG_TYPE + IDEOLOGY_TYPE;
    slantCSV = open(year_prefix + STATIONSLANTSPRE + suffix + '.csv', 'w')   
    slantCsvWriter = csv.DictWriter(slantCSV, fieldnames=['date'] + all_stations)
    slantCsvWriter.writeheader()

    slantCSVSE = open(year_prefix + STATIONSLANTSPRE + 'SE' + suffix + '.csv', 'w')
    slantSeCsvWriter = csv.DictWriter(slantCSVSE, fieldnames=['date'] + all_stations)
    slantSeCsvWriter.writeheader()

    stationdata = None
    if ANALYSIS_TYPE == 'SUMMARY' or ANALYSIS_TYPE == 'MONTHLY':
        stationdata = doAnalysis(year_prefix, slantCsvWriter, slantSeCsvWriter, ANALYSIS_TYPE, years)
    else: # MONTHLY_NGRAMS:
        stationdata = []        
        for year in years:
            for month in range(1,13):
                input_prefix = str(year)+'{0:02d}'.format(month)                
                print '--- Running monthly n-gram analysis for '+input_prefix+' ---'
                station_data = doAnalysis(input_prefix, slantCsvWriter, slantSeCsvWriter, ANALYSIS_TYPE, [year])
                stationdata.append((input_prefix, station_data))
                print '--- DONE '+input_prefix+' ---'
                
    print 'Saving slants pickle.\n'
    savePickle(year_prefix + STATIONSLANTSPRE + suffix + '.pickle', stationdata)

    slantCSV.close()
    slantCSVSE.close()
    print 'Done!'
    

if __name__ == "__main__":
    main(sys.argv)
    