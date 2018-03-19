#!/bin/bash
# Run entire analysis. To run from scratch, either set REBUILD_DATA=True in scripts or remove output/intermediate files.
# (Assumes we have stationngrams already computed for CCs, using parseNewsCCs.py)
#
# USAGE: nohup ./RUNALL.sh &   and then   tail -f nohup.out

#### MONTHLY ANALYSIS: ####
cd CR
echo "___PARSING CRs for each month, year___"
python parseCR.py 2009 11 | tee parseCR-200911.log
python parseCR.py 2009 12 | tee parseCR-200912.log
./parseCRmonths.sh 2010 | tee parseCR-2010monthly.log
./parseCRmonths.sh 2011 | tee parseCR-2011monthly.log
./parseCRmonths.sh 2012 | tee parseCR-2012monthly.log
./parseCRmonths.sh 2013 | tee parseCR-2013monthly.log
./parseCRmonths.sh 2014 | tee parseCR-2014monthly.log
./parseCRmonths.sh 2015 | tee parseCR-2015monthly.log
cd ..

echo "___GenTopPhrases for each year___"
./genTopPhrasesMonthly.sh 2010 | tee genTopPhrases-2010monthly.log
./genTopPhrasesMonthly.sh 2011 | tee genTopPhrases-2011monthly.log
./genTopPhrasesMonthly.sh 2012 | tee genTopPhrases-2012monthly.log
./genTopPhrasesMonthly.sh 2013 | tee genTopPhrases-2013monthly.log
./genTopPhrasesMonthly.sh 2014 | tee genTopPhrases-2014monthly.log
./genTopPhrasesMonthly.sh 2015 | tee genTopPhrases-2015monthly.log

echo "___AnalyzeNgrams___"
python analyzeNgrams.py MONTHLY_NGRAMS 2010 2011 2012 2013 2014 2015 | tee analyzeNgrams-2010-5-MONTHLY_NGRAMS.WLSRob.dwnomc.log

#### SUMMARY ANALYSIS: ####
echo "___COMPUTING SUMMARY___"
cd CR
echo "___PARSING CRs___"
python parseCR.py 2010 2011 2012 2013 2014 2015 | tee parseCR-2010-5.log
cd ..
echo "___GenTopPhrases___"
python genTopPhrases.py 2010 2011 2012 2013 2014 2015 | tee genTopPhrases-2010-5.log
echo "___AnalyzeNgrams___"
python analyzeNgrams.py SUMMARY 2010 2011 2012 2013 2014 2015 | tee analyzeNgrams-2010-5-SUMMARY.WLSRob.dwnomc.log
python analyzeNgrams.py MONTHLY 2010 2011 2012 2013 2014 2015 | tee analyzeNgrams-2010-5-MONTHLY.WLSRob.dwnomc.log

#### RERUN MONTHLY N-GRAM AND SUMMARY FINAL ANALYSES WITH ADA SCORES ####
sed -i "s/IDEOLOGY_TYPE = 'dwnom'/IDEOLOGY_TYPE = 'ada'/" analyzeNgrams.py
echo "___MONTHLY USING ADAs___"
python analyzeNgrams.py MONTHLY_NGRAMS 2010 2011 2012 2013 2014 2015 | tee analyzeNgrams-2010-5-MONTHLY_NGRAMS.WLSRob.adac.log
echo "___SUMMARY USING ADAs___"
python analyzeNgrams.py SUMMARY 2010 2011 2012 2013 2014 2015 | tee analyzeNgrams-2010-5-SUMMARY.WLSRob.adac.log
sed -i "s/IDEOLOGY_TYPE = 'ada'/IDEOLOGY_TYPE = 'dwnom'/" analyzeNgrams.py

echo "RUNALL COMPLETE"