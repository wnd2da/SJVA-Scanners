# -*- coding: UTF-8 -*-
#
# Copyright (c) 2010 Plex Development Team. All rights reserved.
#
#####################################################################################
USE_SEASON_REGEX		= False		#
USE_LOG				= True
#####################################################################################


import re, os, os.path
import Media, VideoFiles, Stack, Utils
from mp4file import mp4file, atomsearch
import time, json, traceback, io

episode_regexps = [
    '(?P<show>.*?)[sS](?P<season>[0-9]+)[\._ ]*[eE](?P<ep>[0-9]+)[\._ ]*([- ]?[sS](?P<secondSeason>[0-9]+))?([- ]?[Ee+](?P<secondEp>[0-9]+))?', # S03E04-E05
    '(?P<show>.*?)[sS](?P<season>[0-9]{2})[\._\- ]+(?P<ep>[0-9]+)',                                                            # S03-03
    '(?P<show>.*?)([^0-9]|^)(?P<season>(19[3-9][0-9]|20[0-5][0-9]|[0-9]{1,2}))[Xx](?P<ep>[0-9]+)((-[0-9]+)?[Xx](?P<secondEp>[0-9]+))?',  # 3x03, 3x03-3x04, 3x03x04
    '(.*?)(^|[\._\- ])+(?P<season>sp)(?P<ep>[0-9]{2,3})([\._\- ]|$)+',  # SP01 (Special 01, equivalent to S00E01)
    #'(.*?)[^0-9a-z](?P<season>[0-9]{1,2})(?P<ep>[0-9]{2})([\.\-][0-9]+(?P<secondEp>[0-9]{2})([ \-_\.]|$)[\.\-]?)?([^0-9a-z%]|$)' # .602.
    '(.*?)[^0-9a-z](?P<season>[0-9]{10,20})(?P<ep>[0-9]{20})([\.\-][0-9]+(?P<secondEp>[0-9]{20})([ \-_\.]|$)[\.\-]?)?([^0-9a-z%]|$)' # .602.
  ]

date_regexps = [
    '(?P<year>[0-9]{4})[^0-9a-zA-Z]+(?P<month>[0-9]{2})[^0-9a-zA-Z]+(?P<day>[0-9]{2})([^0-9]|$)',                # 2009-02-10
    '(?P<month>[0-9]{2})[^0-9a-zA-Z]+(?P<day>[0-9]{2})[^0-9a-zA-Z(]+(?P<year>[0-9]{4})([^0-9a-zA-Z]|$)', # 02-10-2009
  ]

date_regexps2 = [
    '(?P<year>[0-9]{6})'
  ]

standalone_episode_regexs = [
  '(.*?)( \(([0-9]+)\))? - ([0-9]+)+x([0-9]+)(-[0-9]+[Xx]([0-9]+))?( - (.*))?',  # Newzbin style, no _UNPACK_
  '(.*?)( \(([0-9]+)\))?[Ss]([0-9]+)+[Ee]([0-9]+)(-[0-9]+[Xx]([0-9]+))?( - (.*))?'   # standard s00e00
  ]

season_regex = '.*?(?P<season>[0-9]+)$' # folder for a season

just_episode_regexs = [
    '[eE](?P<ep>[0-9]{1,4})',				    # E04
    u'(?P<ep>[0-9]{1,4})[회|화]',
    '(?P<ep>[0-9]{1,3})[\. -_]*of[\. -_]*[0-9]{1,3}',       # 01 of 08
#    '^(?P<ep>[0-9]{1,3})[^0-9]',                           # 01 - Foo 4시 사건반장
    '^(?P<ep>[0-9]{2,3})[^0-9]',                           # 01 - Foo
    'e[a-z]*[ \.\-_]*(?P<ep>[0-9]{2,3})([^0-9c-uw-z%]|$)', # Blah Blah ep234
    '.*?[ \.\-_](?P<ep>[0-9]{2,3})[^0-9c-uw-z%]+',         # Flah - 04 - Blah
    '.*?[ \.\-_](?P<ep>[0-9]{2,3})$',                      # Flah - 04
    '.*?[^0-9x](?P<ep>[0-9]{2,3})$',                       # Flah707
    '^(?P<ep>[0-9]{1,3})$',                                 # 01
    #'(?P<ep>[0-9]{1,4})',
  ]

kor_season_regex = '(\s|시즌)(?P<season>[0-9]{1,2})\s[eE](?P<ep>[0-9]{1,4})'

ends_with_number = '.*([0-9]{1,2})$'

ends_with_episode = ['[ ]*[0-9]{1,2}x[0-9]{1,3}$', '[ ]*S[0-9]+E[0-9]+$']

# Look for episodes.
def Scan(path, files, mediaList, subdirs, language=None, root=None):
  Log('+++++++++++++++++++++ Scan')
  Log('path:%s' % path.encode('euc-kr'))
  Log('files:%s' % files)
  for file in files:
	Log(file.encode('euc-kr'))
  Log('mediaList:%s' % mediaList)
  Log('subdirs:%s' % subdirs)
  for subdir in subdirs:
	Log(subdir.encode('euc-kr'))
  ### Root scan for OS information that i need to complete the Log function ###
  """
  if path == "":
    Log("================================================================================")
    try:
      os_uname=""
      for string in os.uname(): os_uname += string
      Log("os.uname():   '%s'" % os_uname)          #(sysname, nodename, release, version, machine)  #
      Log("Sys.platform: '%s'" % sys.platform)      #
      Log("os.name:      '%s'" % os.name)           # 'posix', 'nt', 'os2', 'ce', 'java', 'riscos'.) 
      Log("os.getcwd:    '%s'" % os.getcwd())       # Current dir: /volume1/homes/plex
      Log("root folder:  '%s'" % root if root is not None else "")
    except: pass
  """

  # Scan for video files.
  VideoFiles.Scan(path, files, mediaList, subdirs, root)
  
  # Take top two as show/season, but require at least the top one.
  paths = Utils.SplitPath(path)
  if len(paths) != 0:
	  Log('>> SCAN PATH : %s' % paths[0].encode('euc-kr'))
  shouldStack = True
  
  if len(paths) == 1 and len(paths[0]) == 0:
  
    # Run the select regexps we allow at the top level.
    for i in files:
      Log('\nFILE1 : %s' % i.encode('euc-kr'))
      try:
        file = os.path.basename(i)
        for rx in episode_regexps[0:-1]:
          match = re.search(rx, file, re.IGNORECASE)
          if match:

            # Extract data.
            show = match.group('show') if match.groupdict().has_key('show') else ''
            season = match.group('season')
            if season.lower() == 'sp':
              season = 0
            episode = int(match.group('ep'))
            endEpisode = episode
            if match.groupdict().has_key('secondEp') and match.group('secondEp'):
              endEpisode = int(match.group('secondEp'))

            # Clean title.
            name, year = VideoFiles.CleanName(show)
            if len(name) > 0:
              for ep in range(episode, endEpisode+1):
                tv_show = Media.Episode(name, season, ep, '', year)
                tv_show.display_offset = (ep-episode)*100/(endEpisode-episode+1)
                tv_show.parts.append(i)
                mediaList.append(tv_show)
      except Exception, e:
        pass
  
  elif len(paths) > 0 and len(paths[0]) > 0:
    done = False
        
    # If we're inside a Plex Versions directory, remove it and the quality directory from consideration.
    if 'Plex Versions' in paths and len(paths) > 2:
      versions_index = paths.index('Plex Versions')
      del paths[versions_index:versions_index + 2]

    # See if parent directory is a perfect match (e.g. a directory like "24 - 8x02 - Day 8_ 5_00P.M. - 6_00P.M")
    if len(files) == 1:
      for rx in standalone_episode_regexs:
        res = re.findall(rx, paths[-1])
        if len(res):
          show, junk, year, season, episode, junk, endEpisode, junk, title = res[0]
          
          # If it didn't have a show, then grab it from the directory.
          if len(show) == 0:
            (show, year) = VideoFiles.CleanName(paths[0])
          else:
            (show, ignore) = VideoFiles.CleanName(show)
            
          episode = int(episode)
          if len(endEpisode) > 0:
            endEpisode = int(endEpisode)
          else:
            endEpisode = episode
            
          for ep in range(episode, endEpisode+1):
            tv_show = Media.Episode(show, season, ep, title, year)
            tv_show.display_offset = (ep-episode)*100/(endEpisode-episode+1)
            tv_show.parts.append(files[0])
            mediaList.append(tv_show)
            
          done = True
	  Log('11111 %s' % tv_show)
          break
          
    if done == False:

      # Not a perfect standalone match, so get information from directories. (e.g. "Lost/Season 1/s0101.mkv")
      season = None
      seasonNumber = None

      (show, year) = VideoFiles.CleanName(paths[0])
      
      # Which component looks like season?
      if len(paths) >= 2:
        season = paths[len(paths)-1]
        match = re.match(season_regex, season, re.IGNORECASE)
        if match:
          seasonNumber = int(match.group('season'))
      
      # Make sure an episode name didn't make it into the show.
      for rx in ends_with_episode:
        show = re.sub(rx, '', show)

      for i in files:
        try:
          Log('FILE2 : %s' % i.encode('euc-kr'))
	except:
	  Log('FILE2 : %s' % i)
        done = False
        file = os.path.basename(i)
        (file, ext) = os.path.splitext(file)
        """
        if ext.lower() in ['.mp4', '.m4v', '.mov']:
          m4season = m4ep = m4year = 0
          m4show = title = ''
          try: 
            mp4fileTags = mp4file.Mp4File(i)
            
            # Show.
            try: m4show = find_data(mp4fileTags, 'moov/udta/meta/ilst/tvshow').encode('utf-8')
            except: pass
              
            # Season.
            try: m4season = int(find_data(mp4fileTags, 'moov/udta/meta/ilst/tvseason'))
            except: pass
              
            # Episode.
            m4ep = None
            try:
              # tracknum (can be 101)
              m4ep = int(find_data(mp4fileTags, 'moov/udta/meta/ilst/tracknum'))
            except:
              try:
                # tvepisodenum (can be S2E16)
                m4ep = find_data(mp4fileTags, 'moov/udta/meta/ilst/tvepisodenum')
              except:
                # TV Episode (can be 101)
                m4ep = int(find_data(mp4fileTags, 'moov/udta/meta/ilst/tvepisode'))
            
            if m4ep is not None:
              found = False
              try:
                # See if it matches regular expression.
                for rx in episode_regexps[:-1]:
                  match = re.search(rx, file, re.IGNORECASE)
                  if match:
                    season = match.group('season')
                    if season.lower() == 'sp':
                      season = 0
                    else:
                      season = int(season)
                    m4season = int(match.group('season'))
                    m4ep = int(match.group('ep'))
                    found = True
              
                if found == False and re.match('[0-9]+', str(m4ep)):
                  # Carefully convert to episode number.
                  m4ep = int(m4ep) % 100
                elif found == False:
                  m4ep = int(re.findall('[0-9]+', m4ep)[0])
              except:
                pass

            # Title.
            try: title = find_data(mp4fileTags, 'moov/udta/meta/ilst/title').encode('utf-8')
            except: pass
              
            # Note: Dates/years embedded in episode files tend to be air or "recorded on" dates, which can 
            # mislead the agent when doing series matching, so we will no longer pass those up as hints here.

            # If we have all the data we need, add it.
            if len(m4show) > 0 and m4season > 0 and m4ep > 0:
              tv_show = Media.Episode(m4show, m4season, m4ep, title, year)
              tv_show.parts.append(i)
              mediaList.append(tv_show)
              continue

          except:
            pass
        """

        # Check for date-based regexps first.
        for rx in date_regexps:
          match = re.search(rx, file)
          if match:

           # Make sure there's not a stronger season/ep match for the same file.
            try:
              for r in episode_regexps[:-1] + standalone_episode_regexs:
                if re.search(r, file):
                  raise
            except:
              break

            year = int(match.group('year'))
            month = int(match.group('month'))
            day = int(match.group('day'))

            # Use the year as the season.
            tv_show = Media.Episode(show, year, None, None, None)
            tv_show.released_at = '%d-%02d-%02d' % (year, month, day)
            tv_show.parts.append(i)
            mediaList.append(tv_show)

            done = True
	    Log('ADD(2) DATE : SHOW-%s / DATE-%s' % (show.encode('euc-kr'), tv_show.released_at))
	    Log('MATCH : %s' % rx)
            break

        if done == False:

          # Take the year out, because it's not going to help at this point.
          cleanName, cleanYear = VideoFiles.CleanName(file)
          if not year and cleanYear:
            year = cleanYear
          if cleanYear != None:
	    #Log(cleanYear)
	    #Log(file)

            file = file.replace(str(cleanYear), 'XXXX')
            
          # Minor cleaning on the file to avoid false matches on H.264, 720p, etc.
          whackRx = ['([hHx][\.]?264)[^0-9]', '[^[0-9](720[pP])', '[^[0-9](1080[pP])', '[^[0-9](480[pP])']
          for rx in whackRx:
            file = re.sub(rx, ' ', file)

          file = re.sub(re.compile('\\b' + re.escape(show).replace('\\ ', '[ \-_.()+]+') + '\\b', re.IGNORECASE), 'SERIES ', file)
          
          for rx in episode_regexps:
            
            match = re.search(rx, file, re.IGNORECASE)
            if match:
              # Parse season and episode.
              the_season = match.group('season')
              if the_season.lower() == 'sp':
                the_season = 0
              else:
                the_season = int(the_season)
              episode = int(match.group('ep'))
              endEpisode = episode
              if match.groupdict().has_key('secondEp') and match.group('secondEp'):
                endEpisode = int(match.group('secondEp'))
                
              # More validation for the weakest regular expression.
              if rx == episode_regexps[-1]:
                
                # Look like a movie? Skip it.
                if re.match('.+ \([1-2][0-9]{3}\)', paths[-1]):
                  done = True
		  Log('33333 %s')
                  break
                  
                # Skip season 0 on the weak regex since it's pretty much never right.
                if the_season == 0:
                  break
                  
                # Make sure this isn't absolute order.
                if seasonNumber is not None:
                  if seasonNumber != the_season:
                    # Something is amiss, see if it starts with an episode numbers.
                    if re.search('^[0-9]+[ -]', file):
                      # Let the episode matcher have it.
                      break
                    
                    # Treat the whole thing as an episode.
                    episode = episode + the_season*100
                    if endEpisode is not None:
                      endEpisode = endEpisode + the_season*100

              for ep in range(episode, endEpisode+1):
                tv_show = Media.Episode(show, the_season, ep, None, year)
                tv_show.display_offset = (ep-episode)*100/(endEpisode-episode+1)
                tv_show.parts.append(i)
                mediaList.append(tv_show)
              
              done = True
	      Log('ADD(4) : SHOW-%s / SEASON-%s / EPISODE-%s' % (show.encode('euc-kr'), the_season, episode))
              break

        if done == False and episode_ignore(show):
	  # 180303 
          for rx in date_regexps2:
            match = re.search(rx, file)
            if match:
             # Make sure there's not a stronger season/ep match for the same file.
              try:
                for r in episode_regexps[:-1] + standalone_episode_regexs:
                  if re.search(r, file):
                    raise
              except:
                break
	      str2 = match.group('year')
              year = int(str2[0:2]) + 2000
              month = int(str2[2:4])
              day = int(str2[4:6])

              # Use the year as the season.
              tv_show = Media.Episode(show, year, None, None, None)
              tv_show.released_at = '%d-%02d-%02d' % (year, month, day)
              tv_show.parts.append(i)
              mediaList.append(tv_show)

              done = True
	      Log('ADD(5): SHOW-%s YEAR-%s' % (show.encode('euc-kr'), year))
	      Log('tv_show.released_at %s' % tv_show.released_at)
              break
	      
        if done == False:
          
          # OK, next let's see if we're dealing with something that looks like an episode.
          # Begin by cleaning the filename to remove garbage like "h.264" that could throw
          # things off.
          #
          (file, fileYear) = VideoFiles.CleanName(file)
	  try:
 	    Log('PARSING FILENAME : %s' % file.encode('euc-kr'))
	  except:
	    Log('PARSING FILENAME ERROR')
	  #Log('FILEYEAR : %s' % fileYear)

          # if don't have a good year from before (when checking the parent folders) AND we just got a good year, use it.
          if not year and fileYear: 
            year = fileYear

          for rx in just_episode_regexs:
            episode_match = re.search(rx, file, re.IGNORECASE)
            if episode_match is not None:
              the_episode = int(episode_match.group('ep'))
              the_season = 1
              
              # Now look for a season.
              if seasonNumber is not None:
                the_season = seasonNumber
                
                # See if we accidentally parsed the episode as season.
                #if the_episode >= 100 and int(the_episode / 100) == the_season:
                #  the_episode = the_episode % 100
              else:
	        if rx == just_episode_regexs[0] and USE_SEASON_REGEX:
		  kor_match = re.search(kor_season_regex, file, re.IGNORECASE)  
		  if kor_match:
		    if the_episode == int(kor_match.group('ep')):
		      the_season = int(kor_match.group('season'))

              # Prevent standalone eps matching the "XX of YY" regex from stacking.
              if rx == just_episode_regexs[2]:
                shouldStack = False

              tv_show = Media.Episode(show, the_season, the_episode, None, year)
              tv_show.parts.append(i)
              mediaList.append(tv_show)
              done = True
              Log('ADD(6) : SHOW-%s / SEASON-%s / EPISODE-%s' % (show.encode('euc-kr'), the_season, the_episode))
              Log('MATCH : %s' % rx)
              break


        if done == False:
	  # 180303 
          for rx in date_regexps2:
            match = re.search(rx, file)
            if match:
             # Make sure there's not a stronger season/ep match for the same file.
              try:
                for r in episode_regexps[:-1] + standalone_episode_regexs:
                  if re.search(r, file):
                    raise
              except:
                break
	      str2 = match.group('year')
              year = int(str2[0:2]) + 2000
              month = int(str2[2:4])
              day = int(str2[4:6])

              # Use the year as the season.
              tv_show = Media.Episode(show, year, None, None, None)
              tv_show.released_at = '%d-%02d-%02d' % (year, month, day)
              tv_show.parts.append(i)
              mediaList.append(tv_show)

              done = True
	      Log('ADD(7): SHOW-%s YEAR-%s' % (show.encode('euc-kr'), year))
	      Log('tv_show.released_at %s' % tv_show.released_at)
              break
	      
        
          
        if done == False:
	  try:
	    Log('>>FAIL: %s' % file.encode('euc-kr'))
            print "Got nothing for:", file
	  except Exception as e:
	    print "XXXXX"
	  #print "Got nothing for:", file
  
  #checkDaumMeta(mediaList)
  # Stack the results.
  if shouldStack:
    Stack.Scan(path, files, mediaList, subdirs)
  

def find_data(atom, name):
  child = atomsearch.find_path(atom, name)
  data_atom = child.find('data')
  if data_atom and 'data' in data_atom.attrs:
    return data_atom.attrs['data']

### Log function ########################################################################################
def Log(s): #need relative path
  if USE_LOG == False: return
  try: 
    s = '[%s] %s' % (time.strftime('%H:%M:%S', time.localtime()), s)
    #with io.open(filename, 'a', encoding='utf-8') as file:
    #  file.write( s + "\r\n" )
    filename = os.path.join(os.path.dirname( os.path.abspath( __file__ ) ), '../../', 'Logs', 'Plex Media Scanner Custom.log')
    with open(filename, 'a') as file:
      file.write( s + "\r\n" )
  except: pass


def episode_ignore(name):
	try:
		Log('EPISODE_IGNORE : %s' % name.encode('euc-kr'))
		#data_json_filename = os.path.join(os.path.dirname( os.path.abspath( __file__ ) ), '../../', 'Plug-in Support', 'Data', 'com.plexapp.agents.daum_tv_series', 'data.json')
		data_json_filename = os.path.join(os.path.dirname( os.path.abspath( __file__ ) ), '../../', 'Plug-in Support', 'Data', 'com.plexapp.agents.daum_movie', 'data.json')
		#Log('data_json: %s' % data_json_filename)
		if os.path.isfile(data_json_filename) :
			with io.open(data_json_filename, 'r', encoding='utf-8') as data_file:    
				data = json.load(data_file)
				data = data['no_episode_data']
			if name.decode('utf-8') in data:
				Log('EPISODE_IGNORE MATCH 1: %s' % name.encode('euc-kr'))			
				return True
		return False
	except:
		Log(traceback.format_exc())
		return False



import sys
reload(sys)
sys.setdefaultencoding('utf-8')

if __name__ == '__main__':
  print "Hello, world!"
  path = sys.argv[1]
  files = [os.path.join(path, file) for file in os.listdir(path)]
  media = []
  Scan(path[1:], files, media, [])
  print "Media:", media
