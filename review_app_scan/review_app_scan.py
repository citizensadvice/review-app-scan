import json
import logging
import os
import re
import subprocess
from argparse import ArgumentParser, Namespace
from datetime import datetime, timedelta, timezone
from typing import Any

from dateutil import parser
from tqdm import tqdm


def run_subprocess(command: str):
    """Runs a subprocess and returns the stdout as a dict. Expects JSON compatable response to command."""

    result = subprocess.run(
        command.split(" "),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    logging.debug(f"> {result=}")
    try:
        response_dict = json.loads(result)
    except json.decoder.JSONDecodeError:
        print(f"> Error: Could not parse response from '{command}' as JSON")
        raise
    return response_dict


def get_subnamespaces(namespace: str) -> list[str]:
    """Returns a string list of all the subnamespaces in the given namespace."""
    subnamespaces = []
    print("> Getting subnamespaces...")
    response = run_subprocess(
        f"kubectl get --namespace {namespace} subnamespaceanchors.hnc.x-k8s.io -o json"
    )
    for items in response["items"]:
        subnamespaces.append(items["metadata"]["name"])
    logging.debug(f"> {subnamespaces=}")
    print(f"> Found  {len(subnamespaces)} subnamespaces in namespace {namespace}.")
    return subnamespaces


def get_helm_chart(namespace: str) -> dict[str, Any]:
    """Returns a dictionary of the helm chart for the given namespace"""
    logging.debug(f"> Getting helm charts for {namespace}...")
    helm_data = run_subprocess(
        f"helm list --namespace {namespace} -o json --time-format=2006-01-02T15:04:05Z07:00"
    )
    logging.debug(f"> {namespace}_{helm_data=}")
    if len(helm_data) != 1:
        print(f"> Error: Expected 1 chart for {namespace}")
    return helm_data[0]


def filter_namespaces(namespaces: list[str], review_app_name: str) -> list[str]:
    print(f"> Finding {review_app_name} review app namespaces...")
    regex = f"review-\d+-{review_app_name}"
    logging.debug(f"> {regex=}")
    filtered_namespaces = []
    for namespace in namespaces:
        logging.debug(f"> Testing '{namespace}' against regex...")
        if re.match(pattern=regex, string=namespace):
            logging.debug(f"> Matched, adding {namespace}")
            filtered_namespaces.append(namespace)
    logging.info(f"> Found {len(filtered_namespaces)} review app namespaces.")
    return filtered_namespaces


def write_output(namespace_list: list[str]):
    GITHUB_OUTPUT = os.environ.get("GITHUB_OUTPUT") or "GITHUB_OUTPUT"
    pr_list = []
    for namespace in namespace_list:
        pr_list.append(namespace.split("-")[1])
    dump = json.dumps({"pr_numbers": pr_list}, separators=(",", ":"))
    output = f"matrix={dump}"
    logging.debug(f"> {output=}")
    with open(GITHUB_OUTPUT, "a") as f:
        f.write(output)


def get_arguments() -> Namespace:
    argparser = ArgumentParser()
    argparser.add_argument(
        "review_app_name",
        type=str,
    )
    argparser.add_argument(
        "namespace",
        type=str,
    )
    argparser.add_argument(
        "--max-age",
        required=False,
        type=int,
        help="Max time since a review app was updated in hours",
        default=72,
    )
    argparser.add_argument(
        "--debug",
        "-d",
        required=False,
        help="Pringt debug info",
        action="store_true",
        default=False,
    )
    args = argparser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO, format="%(message)s"
    )
    logging.debug(f"> {args=}")
    return args


def main():
    args = get_arguments()
    current_time = datetime.now(timezone.utc)
    to_be_deleted = []

    review_app_namespaces = filter_namespaces(
        get_subnamespaces(args.namespace), args.review_app_name
    )
    logging.info(
        f"> Searching for reviews apps not updated for at least {args.max_age} hours..."
    )
    for namespace in tqdm(
        review_app_namespaces,
        leave=False,
    ):
        try:
            chart = get_helm_chart(namespace)
        except:
            logging.error(f"> Error getting chart for {namespace}")
        last_updated = parser.parse(chart["updated"])
        delta = current_time - last_updated
        if delta > timedelta(hours=args.max_age):
            logging.debug(
                f"> Namespace {namespace} is older than {args.max_age} hours. Adding to delete list."
            )
            to_be_deleted.append(namespace)
    logging.info(
        f"> Found {len(to_be_deleted)} review apps to be deleted: {json.dumps(to_be_deleted, indent=2).strip('[],')}"
    )
    logging.info("> Writing output to GITHUB_OUTPUT...")
    logging.debug(f"> {to_be_deleted=}")
    write_output(to_be_deleted)
