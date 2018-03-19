# -*- coding: utf-8 -*-
"""
Created on Thu Apr 17 2014

@author: Justin Briggs
Public domain; for use without restrictions.

A script to read ICPSR Member ID #'s 
(obtainable from http://www.voteview.com/icpsr.htm)

Format:
          1.  Congress Number [4 ch]
          2.  ICPSR ID Number (Current):  corrected ID numbers [6 ch]
          3.  State Code:  2 digit ICPSR State Code [3 ch]
          4.  Congressional District Number (0 if Senate) [2 ch]
          5.  State Name [8 ch]
          6.  Party Code:  100 = Dem., 200 = Repub. [5 ch] (See Parties, below)
          7.  Name (short [13 ch] and long form [25 ch])
"""

# State lookup derived from http://voteview.com/state_codes_icpsr.htm
ICPSR_States = { 41: ('AL','ALABAMA'), 81: ('AK','ALASKA'), 61: ('AZ','ARIZONA'), 42: ('AR','ARKANSAS'), 71: ('CA','CALIFORNIA'), 62: ('CO','COLORADO'), 01: ('CT','CONNECTICUT'), 11: ('DE','DELAWARE'), 43: ('FL','FLORIDA'), 44: ('GA','GEORGIA'), 82: ('HI','HAWAII'), 63: ('ID','IDAHO'), 21: ('IL','ILLINOIS'), 22: ('IN','INDIANA'), 31: ('IA','IOWA'), 32: ('KS','KANSAS'), 51: ('KY','KENTUCKY'), 45: ('LA','LOUISIANA'), 02: ('ME','MAINE'), 52: ('MD','MARYLAND'), 03: ('MA','MASSACHUSETTS'), 23: ('MI','MICHIGAN'), 33: ('MN','MINNESOTA'), 46: ('MS','MISSISSIPPI'), 34: ('MO','MISSOURI'), 64: ('MT','MONTANA'), 35: ('NE','NEBRASKA'), 65: ('NV','NEVADA'), 04: ('NH','NEW HAMPSHIRE'), 12: ('NJ','NEW JERSEY'), 66: ('NM','NEW MEXICO'), 13: ('NY','NEW YORK'), 47: ('NC','NORTH CAROLINA'), 36: ('ND','NORTH DAKOTA'), 24: ('OH','OHIO'), 53: ('OK','OKLAHOMA'), 72: ('OR','OREGON'), 14: ('PA','PENNSYLVANIA'), 05: ('RI','RHODE ISLAND'), 48: ('SC','SOUTH CAROLINA'), 37: ('SD','SOUTH DAKOTA'), 54: ('TN','TENNESSEE'), 49: ('TX','TEXAS'), 67: ('UT','UTAH'), 06: ('VT','VERMONT'), 40: ('VA','VIRGINIA'), 73: ('WA','WASHINGTON'), 56: ('WV','WEST VIRGINIA'), 25: ('WI','WISCONSIN'), 68: ('WY','WYOMING'), 55: ('DC','DISTRICT OF COLUMBIA') } 
# Party affiliation lookup derived from http://www.voteview.com/PARTY3.HTM (cite Ken Martis)
Parties = { 1: 'Federalist', 9: 'Jefferson Republican', 10: 'Anti-Federalist', 11: 'Jefferson Democrat', 13: 'Democrat-Republican', 22: 'Adams', 25: 'National Republican', 26: 'Anti Masonic', 29: 'Whig', 34: 'Whig and Democrat', 37: 'Constitutional Unionist', 40: 'Anti-Democrat and States Rights', 41: 'Anti-Jackson Democrat', 43: 'Calhoun Nullifier', 44: 'Nullifier', 46: 'States Rights', 48: 'States Rights Whig', 100: 'Democrat', 101: 'Jackson Democrat', 103: 'Democrat and Anti-Mason', 104: 'Van Buren Democrat', 105: 'Conservative Democrat', 108: 'Anti-Lecompton Democrat', 110: 'Popular Sovereignty Democrat', 112: 'Conservative', 114: 'Readjuster', 117: 'Readjuster Democrat', 118: 'Tariff for Revenue Democrat', 119: 'United Democrat', 200: 'Republican', 202: 'Union Conservative', 203: 'Unconditional Unionist', 206: 'Unionist', 208: 'Liberal Republican', 212: 'United Republican', 213: 'Progressive Republican', 214: 'Non-Partisan and Republican', 215: 'War Democrat', 300: 'Free Soil', 301: 'Free Soil Democrat', 302: 'Free Soil Whig', 304: 'Anti-Slavery', 308: 'Free Soil American and Democrat', 310: 'American', 326: 'National Greenbacker', 328: 'Independent', 329: 'Ind. Democrat', 331: 'Ind. Republican', 333: 'Ind. Republican-Democrat', 336: 'Anti-Monopolist', 337: 'Anti-Monopoly Democrat', 340: 'Populist', 341: 'People''s', 347: 'Prohibitionist', 353: 'Ind. Silver Republican', 354: 'Silver Republican', 355: 'Union', 356: 'Union Labor', 370: 'Progressive', 380: 'Socialist', 401: 'Fusionist', 402: 'Liberal', 403: 'Law and Order', 522: 'American Labor', 537: 'Farmer-Labor', 555: 'Jackson', 603: 'Ind. Whig', 1060: 'Silver', 1061: 'Emancipationist', 1111: 'Liberty', 1116: 'Conservative Republican', 1275: 'Anti-Jackson', 1346: 'Jackson Republican', 3333: 'Opposition', 4000: 'Anti-Administration', 4444: 'Union', 5000: 'Pro-Administration', 6000: 'Crawford Federalist', 6666: 'Crawford Republican', 7000: 'Jackson Federalist', 7777: 'Crawford Republican', 8000: 'Adams-Clay Federalist', 8888: 'Adams-Clay Republican', 9000: 'Unknown', 9999: 'Unknown' } 

def slices(s, *args):
    '''read fixed-width text with given field lengths as variable arguments list'''
    position = 0
    for length in args:
        yield s[position:position + length].strip()
        position += length

#==============================================================================
def readICPSRFile(filename):
    '''Read the full set of congressmen ids in filename and return them as a list of tuples:
      (CongressNumber, ICPSRMemberID, StateAbbr, StateName, DistrictNumber, PoliticalParty, ShortName, LongName)
    '''
    with open(filename,'r') as f:
        congressmen = []
        for line in f:
            # Split each line in the file; blanks are necessary to avoid *'s
            (CID,blank,ICPSRID,STCODE,DISTNUM,STNAME,blank2,PARTYCODE,NAME,FULLNAME) \
                = slices(line,4,1,5,3,2,8,1,4,13,25)
            try:
                full_statename = ICPSR_States[int(STCODE)][1]
                stateabbr = ICPSR_States[int(STCODE)][0]
            except:
                full_statename = 'None'  # eg, George Washington
                stateabbr = 'NA'
            party = Parties[int(PARTYCODE)]
            congressmen.append( (int(CID),int(ICPSRID),stateabbr,full_statename,int(DISTNUM),party,NAME,FULLNAME) )        
        return congressmen
#==============================================================================
    
def defineDicts(congressmen):
    '''Define congressman lookup tables by icpsr and (icpsr, session)'''
    icpsr = {}
    icpsr_session = {}
    for congressman in congressmen:
        (Session, ICPSRMemberID, StateAbbr, StateName, DistrictNum, PoliticalParty, Name, Fullname) = congressman
        icpsr[ICPSRMemberID] = (Fullname, PoliticalParty) # change of party ==> change of ID
        icpsr_session[(ICPSRMemberID, Session)] = (Fullname, StateAbbr, StateName, DistrictNum, PoliticalParty)
    return (icpsr, icpsr_session)