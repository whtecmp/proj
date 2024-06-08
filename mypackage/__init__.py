import argparse
import requests
import logging
import sys
import pydot

def setup_logger(log_file, debug_mode):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)

    handler = logging.FileHandler(log_file) if log_file else logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger

def get_github_data(token, user, repo, logger):
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }

    base_url = f'https://api.github.com/repos/{user}/{repo}'

    # Get latest 3 releases
    releases_url = f'{base_url}/releases'
    logger.debug(f'Fetching releases from {releases_url}')
    releases_response = requests.get(releases_url, headers=headers)
    if releases_response.status_code == 200:
        releases = releases_response.json()[:3]
    else:
        logger.error(f'Failed to fetch releases: {releases_response.status_code}')
        releases = []

    # Get repo info (stars, forks)
    logger.debug(f'Fetching repo info from {base_url}')
    repo_response = requests.get(base_url, headers=headers)
    if repo_response.status_code == 200:
        repo_info = repo_response.json()
        forks_count = repo_info.get('forks_count', 0)
        stargazers_count = repo_info.get('stargazers_count', 0)
    else:
        logger.error(f'Failed to fetch repo info: {repo_response.status_code}')
        forks_count = 0
        stargazers_count = 0

    # Get contributors
    contributors_url = f'{base_url}/contributors'
    logger.debug(f'Fetching contributors from {contributors_url}')
    contributors_response = requests.get(contributors_url, headers=headers)
    if contributors_response.status_code == 200:
        contributors = contributors_response.json()
        contributors_count = len(contributors)
    else:
        logger.error(f'Failed to fetch contributors: {contributors_response.status_code}')
        contributors_count = 0

    # Get pull requests
    pulls_url = f'{base_url}/pulls?state=all'
    logger.debug(f'Fetching pull requests from {pulls_url}')
    pulls_response = requests.get(pulls_url, headers=headers)
    if pulls_response.status_code == 200:
        pulls = pulls_response.json()
        pulls_count = len(pulls)
    else:
        logger.error(f'Failed to fetch pull requests: {pulls_response.status_code}')
        pulls_count = 0

    # Get contributors pull request counts
    contributors_pulls = {}
    for pr in pulls:
        user = pr['user']['login']
        if user in contributors_pulls:
            contributors_pulls[user] += 1
        else:
            contributors_pulls[user] = 1

    contributors_pulls_sorted = sorted(contributors_pulls.items(), key=lambda item: item[1], reverse=True)

    return {
        'releases': releases,
        'forks_count': forks_count,
        'stargazers_count': stargazers_count,
        'contributors_count': contributors_count,
        'pulls_count': pulls_count,
        'contributors_pulls_sorted': contributors_pulls_sorted
    }

def print_github_data(data):
    print("Latest 3 releases:")
    for release in data['releases']:
        print(f"- {release['name']} (tag: {release['tag_name']})")

    print(f"\nNumber of forks: {data['forks_count']}")
    print(f"Number of stars: {data['stargazers_count']}")
    print(f"Number of contributors: {data['contributors_count']}")
    print(f"Number of pull requests: {data['pulls_count']}")

    print("\nContributors sorted by number of pull requests:")
    for contributor, pr_count in data['contributors_pulls_sorted']:
        print(f"- {contributor}: {pr_count} pull requests")


def get_parent_commit(token, user, repo, commit, logger):
    commit_hash = commit['sha']
    url = f"https://api.github.com/repos/{user}/{repo}/commits/{commit['parents'][0]['sha']}"
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }

    try:
        logger.info(f"Fetching commit information for commit '{commit_hash}'")
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

        parent_commit = response.json()

        logger.debug(f"Parent commit hash for commit '{commit_hash}' is: {commit['parents'][0]['sha']}")
        return parent_commit

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch commit information for commit '{commit_hash}': {e}")
        return None

def get_commits_for_branch(token, user, repo, branch_name):
    # GitHub API endpoint for fetching pull requests merged into master
    url = f"https://api.github.com/repos/{user}/{repo}/pulls"
    params = {
        "state": "closed",
        "base": "master",
        "per_page": 100  # Increase per_page to fetch more PRs if needed
    }
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Send GET request to GitHub API
    response = requests.get(url, params=params, headers=headers)

    # Check if request was successful
    if response.status_code == 200:
        pull_requests = response.json()

        # Check if the provided branch name exists among merged branches
        for pr in pull_requests:
            if pr['head']['ref'] == branch_name and pr['merged_at']:
                commits_url = pr['commits_url'].replace("{/sha}", "")  # Remove unnecessary part from URL

                # Fetch commits for the current branch
                response_commits = requests.get(commits_url, headers=headers)
                if response_commits.status_code == 200:
                    commits = response_commits.json()
                    merged_commit_hash = pr['merge_commit_sha'] if pr['merge_commit_sha'] else None

                    # Return all commits and merged commit hash
                    return commits, merged_commit_hash
                else:
                    logger.error(f"Failed to fetch commits for branch '{branch_name}'. Status Code: {response_commits.status_code}")
                    return None, None  # Failed to fetch commits
        else:
            logger.warning(f"No merged pull request found for branch '{branch_name}'.")
            return None, None  # Branch name not found among merged branches
    else:
        logger.error(f"Failed to fetch pull requests. Status Code: {response.status_code}")
        return None, None  # Failed to fetch pull requests


def create_commit_graph(token, user, repo, branch_name, output_file, logger):
    # Fetch commits for the specified branch and get merged commit hash
    commits, merged_commit_hash = get_commits_for_branch(token, user, repo, branch_name)
    if not commits:
        logger.error(f"Failed to fetch commits for branch '{branch_name}'. Exiting.")
        return None
    
    # Add last commit before branch-out 
    parent_commit = get_parent_commit(token, user, repo, commits[0], logger)
    commits = [parent_commit] + commits

    # Initialize a directed graph
    graph = pydot.Dot(graph_type='digraph')

    # Add nodes for each commit
    nodes = {}
    for commit in commits:
        node = pydot.Node(commit['sha'], label=commit['commit']['message'].splitlines()[0])
        graph.add_node(node)
        nodes[commit['sha']] = node

    # Add merged commit hash as the last node in the graph
    if merged_commit_hash:
        merged_node = pydot.Node(merged_commit_hash, label=f"Merged Commit: {merged_commit_hash[:7]}")
        graph.add_node(merged_node)

        # Add edge from last commit to merged commit
        last_commit_sha = commits[-1]['sha']
        if last_commit_sha in nodes:
            edge_to_merged = pydot.Edge(nodes[last_commit_sha], merged_node)
            graph.add_edge(edge_to_merged)
        else:
            logger.warning(f"Last commit SHA '{last_commit_sha}' not found among nodes.")

    # Add edges between commits (parent relationships)
    for commit in commits:
        sha = commit['sha']
        parents = commit['parents']
        for parent in parents:
            parent_sha = parent['sha']
            if parent_sha in nodes:
                is_first_commit = False
                edge = pydot.Edge(nodes[parent_sha], nodes[sha])
                graph.add_edge(edge)

    first_commit_sha = commits[0]['sha']  # Assuming last commit in list is the oldest
    first_commit_node = nodes[first_commit_sha]
    edge_to_merge = pydot.Edge(first_commit_node, merged_node)
    graph.add_edge(edge_to_merge)

    # Write the graph to a .dot file
    graph.write(output_file)
    logger.info(f"Commit graph generated and saved as '{output_file}'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Get GitHub repository information and create commit graph.')
    parser.add_argument('token', help='GitHub token')
    parser.add_argument('user', help='GitHub username')
    parser.add_argument('repo', help='GitHub repository name')
    parser.add_argument('--log_to_file', metavar='LOG_FILE', help='Log to a specified file instead of stdout')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--branch', help='Branch to create commit graph for')
    parser.add_argument('--graph_file', default='commit_graph.dot', help='Specify the graph file (default: commit_graph.dot)')

    args = parser.parse_args()

    logger = setup_logger(args.log_to_file, args.debug)

    github_data = get_github_data(args.token, args.user, args.repo, logger)
    print_github_data(github_data)

    if args.branch:
        create_commit_graph(args.token, args.user, args.repo, args.branch, args.graph_file, logger)

