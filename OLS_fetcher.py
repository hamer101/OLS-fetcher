import re
import json
import requests
from bs4 import BeautifulSoup

# Login page and logging in action addresses
# Login details, with login and password to be provided by user
# Credentials (to be cropped out of the course page) passed to GET anwsers
LOGIN_GET  = 'https://app.erasmusplusols.eu/'
LOGIN_POST = 'https://app.erasmusplusols.eu/auth/login/user'
COURSE     = 'https://app.erasmusplusols.eu/gw//lcapi/main/api/lc/user-learning-paths/language/en_GB'
login_details = {'_token'   : '',
                 'login'    : '',
                 'password' : ''}
credentials = {'x-altissia-token'  : '',
               'x-device-uuid'     : ''}

def recieveCredentials(line: str) -> str:
    """
    Takes in the string of page's <script></script> tag's line containing the
    credentials and returns a stripped string containing it.
    """
    
    matches = re.findall(r"\'[^\']*\'", line)
    return matches[1].strip('\'')

def checkType(obj) -> bool:
    """
    Returns True if the passed object is a list of strings and False otherwise
    """
    return isinstance(obj, list) and all(isinstance(elem, str) for elem in obj)

def printItems(obj, indent=0, list_type = 'ul') -> str:
    """
    A recursive function taking in a dictionary (which may contain strings,
    dictionaries and lists) and recursive key values of indent and list_type.
    Produces a string representing tree of nested html lists.
    """
    html_list = ''
    tabulation = '  ' * indent
    if len(obj):
        if isinstance(obj, str):
            html_list += f'{tabulation}<li>{obj}</li>\n'
        else:
            html_list += f'{tabulation}<{list_type}>\n'
            if isinstance(obj, dict):
                obj = list(obj.values())
            for v in obj:
                if checkType(v) and len(v) > 1:
                    html_list += printItems(v, indent+1, 'ol')
                else:
                    html_list += printItems(v, indent+1)
            html_list += f'{tabulation}</{list_type}>\n'
            
    return html_list

with requests.Session() as s:
    # Signing in
    login_page = s.get(LOGIN_GET)
    login_soup = BeautifulSoup(login_page.text, 'html5lib')
    token = login_soup.find('input', {'name':'_token'}).get('value')            # An addtitional verification token is placed in a hidden input field
    login_details['_token'] = token
    dashboard_page = s.post(LOGIN_POST, data=login_details)
    
    # Cropping credentials to be passed in GET method yielding json files
    dashboard_soup = BeautifulSoup(dashboard_page.text, 'html5lib')
    credential_script = dashboard_soup.find_all('script')
    credential_lines = str(list(credential_script[3].children)[0]).splitlines() # Device uuid and altissia token are placed in the 3rd script field 
    credentials['x-device-uuid'] = recieveCredentials(credential_lines[5])
    credentials['x-altissia-token'] = recieveCredentials(credential_lines[6])

    # Getting a json of missions and preparing a list of lessons' IDs within each
    missions_page = s.get(COURSE, headers = credentials)
    missions_dict = json.loads(missions_page.text)
    lessons_list = [lessons_val['externalId']
                    for mission_val in missions_dict['missions'][104:]
                    for lessons_val in mission_val['lessons']]
    
    # Preparing a list of lesson dictionaries, containing lesson's title and a list
    # of related activities dictionaries, each labeled with the activity type, its ID
    # obligatoriness flag and, if it's the case for it, the correct anwsers
    curriculum = []
    for lesson in lessons_list:
        activities_list = [] 
        
        activities_url = f'https://app.erasmusplusols.eu/gw//lcapi/main/api/lc/lessons/{lesson}'
        activities_page = s.get(activities_url, headers = credentials)
        activities_dict_raw = json.loads(activities_page.text)
           
        no_summary_test = False if activities_dict_raw['activities'][-1]['activityType'] == 'SUMMARY_TEST' else True

        for activity in activities_dict_raw['activities']:
            activity_id = activity['externalId']
            activity_dict = {'activityType'     : activity['activityType'],
                             'externalId'       : activity_id,
                             'obligatoriness'   : no_summary_test}    

            if activity['activityType'] == 'SUMMARY_TEST' or activity['activityType'] == 'EXERCISE':

                answers_url = f'{activities_url}/activities/{activity_id}?translationLg=en_GB'
                answers_page = s.get(answers_url, headers = credentials)
                answers_dict_raw = json.loads(answers_page.text)
                answers_items_dict = answers_dict_raw['content']['items']
                answers = [item['correctAnswers'][0][0] for item in answers_items_dict] # At times more than one answer is correct, we take the 1st

                if activity['activityType'] == 'SUMMARY_TEST': 
                    activity_dict['obligatoriness'] = True 
                    
                activity_dict['answers'] = answers

            activities_list.append(activity_dict)

        curriculum.append({'title'      : lesson,
                           'activities' : activities_list})
    
# Composing a list of lesson dictionaries filled with a title and a 'must do' list
# containing activities necessary for passing the course, each activity being a
# dictionary with the type and what do fields, the second one being either a str or a list
necessity = []
for lesson in curriculum:
    necessary_activities = [{'Type'    : activity['activityType'] + ': ' + activity['externalId'].lower(),
                             'What do' : activity.get('answers', ['Just click it'])}    # If there're no anwsers, we insert a string
                            for activity in lesson['activities'] if activity['obligatoriness'] == True]

    necessary_lesson = {'Title'    : lesson['title'],
                        'Must do' : necessary_activities}
    necessity.append(necessary_lesson)
    
# Printing out the lists    
with open('list.html','w', encoding = 'utf-8') as f:
    f.write(printItems(necessity))