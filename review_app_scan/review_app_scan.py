from datetime import datetime, timezone, timedelta
from kubernetes import client as k8s, config
import argparse, re, json, subprocess, dateutil, logging
from typing import Any


def get_namespaces() -> list[str]:
    """Returns a string list of all the namespaces in the cluster."""

    print("> Getting namespaces...")
    api = k8s.CoreV1Api()
    namespaces = [namespace.metadata.name for namespace in api.list_namespace().items]
    logging.debug(f"> {namespaces=}")
    print(f"> Found  {len(namespaces)} namespaces.")
    return namespaces


def get_subnamespaces(namespace: str) -> list[str]:
    """Returns a string list of all the subnamespaces in the given namespace."""

    print("> Getting subnamespaces...")
    api = k8s.CustomObjectsApi()
    subnamespaces = [
        namespace.metadata.name
        for namespace in api.list_namespaced_custom_object(
            group="hnc.x-k8s.io",
            version="apiextensions.k8s.io/v1",
            namespace=namespace,
            plural="subnamespaceanchors",
        ).items
    ]
    logging.debug(f"> {subnamespaces=}")
    print(f"> Found  {len(subnamespaces)} namespaces.")
    return subnamespaces


def get_helm_chart(namespace: str) -> dict[Any]:
    """Returns a dictionary of the helm chart for the given namespace"""
    logging.debug(f"> Getting helm charts for {namespace}...")
    result = subprocess.run(
        [
            "helm",
            "list",
            "--namespace",
            namespace,
            "-o",
            "json",
            "--time-format",
            "2006-01-02T15:04:05Z07:00",
        ],
        capture_output=True,
        text=True,
        check=True,  # Check for command execution success
    )
    helm_data = json.loads(result.stdout)
    logging.debug(f"> {namespace}_{helm_data=}")
    if len(helm_data) != 1:
        print(f"> Error: Expected 1 chart for {namespace}")
    return helm_data[0]


def filter_namespaces(namespaces: list[str], review_app_name: str) -> list[str]:
    print(f"> Finding {review_app_name} review app namespaces...")
    regex = f"review-\d{{1,4}}-{review_app_name}"
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
    pr_list = []
    for namespace in namespace_list:
        pr_list.append(namespace.split("-")[1])
    dump = json.dumps({"pr_numbers": pr_list})
    output = f"matrix={dump}"
    logging.debug(f"> {output=}")
    with open("GITHUB_OUTPUT", "w") as f:
        f.write(output)


def get_arguments() -> dict:
    argparser = argparse.ArgumentParser()
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
    config.load_kube_config()
    current_time = datetime.now(timezone.utc)
    to_be_deleted = []

    review_app_namespaces = filter_namespaces(
        get_subnamespaces(args.namespace), args.review_app_name
    )
    logging.info(
        f"> Searching for reviews apps not updated for at least {args.max_age} hours..."
    )
    for namespace in review_app_namespaces:
        try:
            chart = get_helm_chart(namespace)
        except:
            logging.error(f"> Error getting chart for {namespace}")
        last_updated = dateutil.parser.parse(chart["updated"])
        delta = current_time - last_updated
        if delta > timedelta(hours=args.max_age):
            logging.debug(
                f"> Namespace {namespace} is older than {args.max_age} hours. Adding to delete list."
            )
            to_be_deleted.append(namespace)
    logging.info(
        f"> Found {len(to_be_deleted)} review apps to be deleted: {json.dumps(to_be_deleted,indent=2).strip('[],')}"
    )
    logging.debug(f"> Writing output to GITHUB_OUTPUT...")
    write_output(to_be_deleted)
