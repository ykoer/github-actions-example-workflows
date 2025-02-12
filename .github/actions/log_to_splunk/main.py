import os
import requests
import json
import zipfile
import io
import glob
import re
from datetime import datetime

def main():
    GITHUB_REF=os.environ["GITHUB_REF"]
    GITHUB_REPOSITORY=os.environ["GITHUB_REPOSITORY"]
    GITHUB_RUN_ID=os.environ["GITHUB_RUN_ID"]
    GITHUB_API_URL=os.environ["GITHUB_API_URL"]
    GITHUB_WORKFLOWID=os.environ["INPUT_WORKFLOW_ID"]
    GITHUB_TOKEN = os.environ.get("INPUT_GITHUB_TOKEN")

    SPLUNK_HEC_URL=os.environ["INPUT_SPLUNK_URL"]+"services/collector/event"
    SPLUNK_HEC_TOKEN=os.environ["INPUT_HEC_TOKEN"]
    SPLUNK_SOURCE=os.environ["INPUT_SOURCE"]
    SPLUNK_SOURCETYPE=os.environ["INPUT_SOURCETYPE"]

    batch = count = 0
    eventBatch = ""
    headers = {"Authorization": "Splunk "+SPLUNK_HEC_TOKEN}
    host=os.uname()[1]

    summary_url = f"{GITHUB_API_URL}/repos/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_WORKFLOWID}"

    # print("######################")
    # print(f"GITHUB_REF: {GITHUB_REF}")
    # print(f"GITHUB_REPOSITORY: {GITHUB_REPOSITORY}")
    # print(f"GITHUB_RUN_ID: {GITHUB_RUN_ID}")
    # print(f"GITHUB_API_URL: {GITHUB_API_URL}")
    # print(f"GITHUB_WORKFLOWID: {GITHUB_WORKFLOWID}")
    # print(f"GITHUB_TOKEN: {GITHUB_TOKEN}")
    # print(f"SPLUNK_HEC_URL: {SPLUNK_HEC_URL}")
    # print(f"SPLUNK_HEC_TOKEN: {SPLUNK_HEC_TOKEN}")
    # print(f"SPLUNK_SOURCE: {SPLUNK_SOURCE}")
    # print(f"SPLUNK_SOURCETYPE: {SPLUNK_SOURCETYPE}")
    # print(f"host: {host}")
    # print(f"headers: {headers}")
    # print(f"summary_url: {summary_url}")
    # print("######################")
    # for key, value in os.environ.items():
    #     print(f'{key}={value}')
    # print("######################")

    try:
        x = requests.get(summary_url, stream=True, auth=('token',GITHUB_TOKEN))
        x.raise_for_status()
    except requests.exceptions.HTTPError as errh:
        output = "GITHUB API Http Error:" + str(errh)
        print(f"Error: {output}")
        print(f"::set-output name=result::{output}")
        return x.status_code
    except requests.exceptions.ConnectionError as errc:
        output = "GITHUB API Error Connecting:" + str(errc)
        print(f"Error: {output}")
        print(f"::set-output name=result::{output}")
        return x.status_code
    except requests.exceptions.Timeout as errt:
        output = "Timeout Error:" + str(errt)
        print(f"Error: {output}")
        print(f"::set-output name=result::{output}")
        return x.status_code
    except requests.exceptions.RequestException as err:
        output = "GITHUB API Non catched error conecting:" + str(err)
        print(f"Error: {output}")
        print(f"::set-output name=result::{output}")
        return x.status_code
    except Exception as e:
        print("Internal error", e)
        return x.status_code

    summary = x.json()

    summary.pop('repository')

    summary["repository"]=summary["head_repository"]["name"]
    summary["repository_full"]=summary["head_repository"]["full_name"]

    summary.pop('head_repository')

    utc_time = datetime.strptime(summary["updated_at"], "%Y-%m-%dT%H:%M:%SZ")
    epoch_time = (utc_time - datetime(1970, 1, 1)).total_seconds()

    event={'event':json.dumps(summary),'sourcetype':SPLUNK_SOURCETYPE,'source':'workflow_summary','host':host,'time':epoch_time}
    event=json.dumps(event)
    print(event)

    #x=requests.post(SPLUNK_HEC_URL, data=event, headers=headers)


    url = f"{GITHUB_API_URL}/repos/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_WORKFLOWID}/logs"
    print(url)

    try:
        x = requests.get(url, stream=True, auth=('token',GITHUB_TOKEN))

    except requests.exceptions.HTTPError as errh:
        output = "GITHUB API Http Error:" + str(errh)
        print(f"Error: {output}")
        print(f"::set-output name=result::{output}")
        return
    except requests.exceptions.ConnectionError as errc:
        output = "GITHUB API Error Connecting:" + str(errc)
        print(f"Error: {output}")
        print(f"::set-output name=result::{output}")
        return
    except requests.exceptions.Timeout as errt:
        output = "Timeout Error:" + str(errt)
        print(f"Error: {output}")
        print(f"::set-output name=result::{output}")
        return
    except requests.exceptions.RequestException as err:
        output = "GITHUB API Non catched error conecting:" + str(err)
        print(f"Error: {output}")
        print(f"::set-output name=result::{output}")
        return

    z = zipfile.ZipFile(io.BytesIO(x.content))
    log_folder = '/tmp'
    z.extractall(log_folder)

    timestamp = batch = count = 0

    for name in glob.glob(f'{log_folder}/*.txt'):
        if os.path.basename(name).startswith('-'):
            continue
        logfile = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name.replace('./','')),'r')
        lines = logfile.readlines()
        count = 0
        batch_number = 1
        for line in lines:
            if line:
                count+=1
                if timestamp:
                    t2=timestamp
                timestamp = re.search(r"\d{4}-\d{2}-\d{2}T\d+:\d+:\d+\.\d+Z", line.strip())

                if timestamp:
                    timestamp = re.sub(r"\dZ","",timestamp.group())
                    timestamp = datetime.strptime(timestamp,"%Y-%m-%dT%H:%M:%S.%f")
                    timestamp = (timestamp - datetime(1970,1,1)).total_seconds()
                else:
                    timestamp=t2

                # find empty lines and skip them
                x = re.sub(r"\d{4}-\d{2}-\d{2}T\d+:\d+:\d+.\d+Z","",line.strip())
                x=x.strip()
                job_name=re.search(r"\/\d+\_(?P<job>.*)\.txt",name)
                job_name=job_name.group('job')
                fields = {'github_run_id':GITHUB_RUN_ID,'github_workflow_id':GITHUB_WORKFLOWID,'github_job_name':job_name,'line_number':count}
                if x:
                    batch+=1
                    event={'event':x,'sourcetype':SPLUNK_SOURCETYPE,'source':SPLUNK_SOURCE,'host':host,'time':timestamp,'fields':fields}
                    eventBatch=eventBatch+json.dumps(event)

                # push every 1000 log lines to splunk as a batch
                if batch>=1000:
                    print(f'log_file={name}, batch_number={batch_number}, line_number={count}')
                    batch=0

                    # x=requests.post(SPLUNK_HEC_URL, data=eventBatch, headers=headers)
                    # print(f'log_file={name}, batch_number={batch_number}, line_number={count}, request_status_code:{x.status_code}')
                    eventBatch=""
                    batch_number+=1
                break

        # push the last batch
        if batch>0:
            # print(f'log_file={name}, batch_number={batch_number}, line_number={count}')
            x=requests.post(SPLUNK_HEC_URL, data=eventBatch, headers=headers)
            print(f'log_file={name}, batch_number={batch_number}, line_number={count}, request_status_code:{x.status_code}')
            eventBatch=""

if __name__ == '__main__':
    main()
