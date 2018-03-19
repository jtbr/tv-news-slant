# -*- coding: utf-8 -*-
"""
Created on Tue Sep 29 18:47 2016

Searches the congressional record for a given set of n-grams (typically 
"top" n-grams) and finds:
1) all permutations of phrases that lead to an n-gram, 
2) a sample of sentences in which the n-gram occurs.

Input: speechfile containing parsed CR documents sorted into speeches by speaker to search
       n-gram file containing n-grams to look for
Outputs: usages file with two hashes containing all permutations, and sample 
         sentences respectively

@author: Justin
"""

import sys, re, random
from collections import defaultdict
from datetime import date
import nltk.data
from nltk.util import ngrams as nltk_ngrams
from nltk.stem.porter import PorterStemmer


sys.path.append('..') # add parent dir to import search path
from common import stopwords, loadPickle, savePickle

# flag to ignore any pickle files and regenerate data from scratch
REBUILD_DATA = False

ps = PorterStemmer()
sent_detector = nltk.data.load('tokenizers/punkt/english.pickle')

SENTENCE_COUNT = 0
WORD_COUNT = 0

# probability of saving a sentence as an example usage
SAMPLE_PROB = 0.1

top_ngrams = set()
procedural_ngrams = set()
found_permutations = defaultdict(set)
sentence_examples = defaultdict(list)

def nextmonth(month,year):
    """return date for first day of next month, given month, year as strings"""
    month = int(month)+1
    year = int(year)
    if month==13:
        month=1
        year = year+1    
    return date(year,month,1)

def tokenizeAndFind(speaker, filename, speech):
    """Tokenize a speech (given by speaker and coming from filename), and search
    for usages of top ngrams, saving all permutations and a sample of sentences."""
    # make speeches a big long string if it isn't already
    if type(speech)==list:
        speech='\n'.join(speech)
    startingLetter = re.compile('^[a-z]')
    
    global top_ngrams, found_permutations, sentence_examples, procedural_ngrams
    
    ## first remove stop words
    sentences = sent_detector.tokenize(speech)
    for sentence_orig in sentences:
        sentence = sentence_orig.lower()
        words_orig = nltk.tokenize.word_tokenize(sentence)
        words = [word for word in words_orig if startingLetter.match(word)] # drop 's, numbers, punctuation, etc
        words = [word for word in words if word not in stopwords] # drop stopwords
        stems = [ps.stem(word) for word in words] # stem words

        bigrams = [ng for ng in nltk_ngrams(stems,2)]
        trigrams = [ng for ng in nltk_ngrams(stems,3)]
        found_ngrams = top_ngrams.intersection(set(bigrams + trigrams))
        if found_ngrams:
            stems_orig = [ps.stem(word) for word in words_orig]
            for ngram in found_ngrams:
                if speaker.find('SPEAKER')>=0 \
                  or speaker.find('PRESIDENT')>=0 \
                  or speaker.find('PRESIDING')>=0 \
                  or speaker.find('CHAIR')>=0:
                    procedural_ngrams.add(ngram)
                    continue
                permutations = found_permutations[ngram]
                try:
                    word1_idx = stems_orig.index(ngram[0])
                    wordN_idx = stems_orig.index(ngram[-1])
                except:
                    print "trouble  finding ngram "+str(ngram)+" in sentence:\n\t"+sentence_orig
                    continue
                if (word1_idx>=wordN_idx):
                    try:
                        wordN_idx = stems_orig.index(ngram[-1], word1_idx+1) #start from after first word location
                    except: 
                        print "trouble2 finding ngram "+str(ngram)+" in sentence:\n\t"+sentence_orig
                        continue
                if (word1_idx < wordN_idx):
                    try:
                        # search reverse-ordered stems from N to 1 looking for another match to ngram[0]
                        offset = stems_orig[wordN_idx:word1_idx:-1].index(ngram[0])
                        word1_idx = wordN_idx - offset
                    except:
                        pass # this just means we didn't have duplicate words
                    sentence_tuple = (speaker, filename, sentence_orig)
                    permutation = " ".join(words_orig[word1_idx:wordN_idx+1])
                    if not permutation in permutations:
                        permutations.add(permutation)
                        found_permutations[ngram] = permutations
                        sentence_examples[ngram] += sentence_tuple
                    else:
                        # SAMPLE_PROB % of the time, save the sentence
                        if (random.uniform(0,1) < SAMPLE_PROB):
                            sentence_examples[ngram] += sentence_tuple

                else:
                    print "trouble3 finding ngram "+str(ngram)+" in sentence:\n\t"+sentence_orig
                    # note, we may find cases where the stems appear more than twice in a sentence
                    continue


def main(args):
    if len(args) < 3:
        print 'Usage: findPhraseUsages [n-grams file] [speeches file]'
        # e.g., 201108bigrams_top.pickle CR/2011speeches.pickle
        exit()
    else:        
        NGRAMFILE = args[1]
        SPEECHFILE = args[2]

    # load speaker-parsed speeches
    speeches = loadPickle(SPEECHFILE)
    if not speeches:
        print "Error: Unable to find speech file: "+SPEECHFILE
        exit()

    # load top n-gram file of n-grams to seek
    ngrams = loadPickle(NGRAMFILE)
    if not ngrams:
        print "Error: Unable to find n-grams file: "+NGRAMFILE
        exit()
    
    global top_ngrams # also, we read read sentence_examples, found_permutations, procedural_ngrams
    top_ngrams = set([tuple(ngram.split(',')) for (ngram,chisq,demcount,repcount) in ngrams])

    print "Searching for phrase usages..."   
    for (speaker, speechTuples) in speeches.viewitems():
        for (filename, docDate, speech) in speechTuples:
            # find usages and populate found_permutations and sentence_examples
            tokenizeAndFind(speaker, filename, speech)
                    
    usages = (top_ngrams, found_permutations, sentence_examples, procedural_ngrams)
    print found_permutations
    print "NGRAMS WITH PROCEDURAL USAGE:"
    print procedural_ngrams
    savePickle("PhraseUsages.pickle.bz2", usages)
    print 'Phrase usage search complete.'

if __name__ == "__main__":
    main(sys.argv)