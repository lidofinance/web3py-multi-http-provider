#!/usr/bin/env python3
"""
PyPI OIDC Trusted Publishing Upload Script

Exchanges OIDC token for PyPI API token and uploads packages using twine.
Replicates the functionality of pypa/gh-action-pypi-publish.
"""
import os
import sys
import subprocess
import argparse
import requests
from pathlib import Path


def exchange_oidc_token(oidc_token: str, token_exchange_url: str) -> str:
    """Exchange OIDC token for PyPI API token."""
    print(f"📤 Exchanging OIDC token at {token_exchange_url}...")
    try:
        mint_token_resp = requests.post(
            token_exchange_url,
            json={'token': oidc_token},
            timeout=5
        )
        
        if not mint_token_resp.ok:
            try:
                error_payload = mint_token_resp.json()
                errors = error_payload.get('errors', [])
                error_messages = '\n'.join(
                    f"  - {err.get('code', 'unknown')}: {err.get('description', 'no description')}"
                    for err in errors
                )
                print(f"❌ Token exchange failed:")
                print(error_messages)
                print("\n💡 This usually means:")
                print("   - Trusted publisher configuration doesn't match")
                print("   - Repository, workflow, or environment name mismatch")
                print("   - Project name mismatch")
            except:
                print(f"❌ Token exchange failed: HTTP {mint_token_resp.status_code}")
                print(f"Response: {mint_token_resp.text[:500]}")
            sys.exit(1)
        
        mint_token_payload = mint_token_resp.json()
        pypi_token = mint_token_payload.get('token')
        
        if not pypi_token:
            print("❌ Token exchange response missing 'token' field")
            print(f"Response: {mint_token_payload}")
            sys.exit(1)
        
        print("✅ Successfully exchanged OIDC token for PyPI API token")
        return pypi_token
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Token exchange request failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error during token exchange: {e}")
        sys.exit(1)


def upload_packages(repository_url: str, skip_existing: bool = False) -> int:
    """Upload packages to PyPI using twine."""
    print("📤 Uploading packages with twine...")
    dist_dir = Path("dist")
    dist_files = list(dist_dir.glob("*"))
    
    if not dist_files:
        print("❌ No distribution files found in dist/")
        sys.exit(1)
    
    oidc_token = os.environ.get('OIDC_TOKEN')
    token_exchange_url = os.environ.get('TOKEN_EXCHANGE_URL')
    
    if not oidc_token:
        print("❌ OIDC token not found")
        sys.exit(1)
    
    if not token_exchange_url:
        print("❌ Token exchange URL not found")
        sys.exit(1)
    
    # Exchange OIDC token for PyPI API token
    pypi_token = exchange_oidc_token(oidc_token, token_exchange_url)
    
    # Set up twine environment
    os.environ['TWINE_USERNAME'] = '__token__'
    os.environ['TWINE_PASSWORD'] = pypi_token
    
    # Build twine command
    twine_cmd = [
        'twine', 'upload',
        '--repository-url', repository_url,
        '--verbose'
    ]
    
    if skip_existing:
        twine_cmd.append('--skip-existing')
    
    twine_cmd.extend([str(f) for f in dist_files])
    
    # Run twine upload
    result = subprocess.run(
        twine_cmd,
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description='Upload Python packages to PyPI using OIDC trusted publishing'
    )
    parser.add_argument(
        '--repository-url',
        required=True,
        help='PyPI repository URL (e.g., https://upload.pypi.org/legacy/ or https://test.pypi.org/legacy/)'
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip uploading files that already exist on PyPI'
    )
    
    args = parser.parse_args()
    
    exit_code = upload_packages(
        repository_url=args.repository_url,
        skip_existing=args.skip_existing
    )
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
