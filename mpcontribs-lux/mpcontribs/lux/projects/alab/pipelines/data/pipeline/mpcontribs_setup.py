#!/usr/bin/env python3
"""
MPContribs Project Setup

Creates/updates empty MPContribs project with metadata only.
Does NOT upload data - that goes to S3.

This module handles:
- Creating new MPContribs projects
- Updating project metadata (title, authors, description, references)
- No column definitions
- No data upload
"""

import os
import logging
from typing import Dict, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class MPContribsProjectManager:
    """Manage MPContribs project metadata (empty config only)"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize MPContribs manager.
        
        Args:
            api_key: Materials Project API key (or set MP_API_KEY env var)
        """
        self.api_key = api_key or os.getenv('MP_API_KEY') or os.getenv('ALAB_MP_API_KEY')
        
        if not self.api_key:
            raise ValueError(
                "MP API key required. Set MP_API_KEY or ALAB_MP_API_KEY environment variable, "
                "or pass api_key parameter"
            )
        
        self._mpr = None
        self._client = None
    
    def _get_mprester(self):
        """Get MPRester instance (lazy load)"""
        if self._mpr is None:
            try:
                from mp_api.client import MPRester
                self._mpr = MPRester(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "mp-api package required. Install with: pip install mp-api>=0.45.13"
                )
        return self._mpr
    
    def _get_client(self, project_name: str):
        """Get ContribsClient instance (lazy load)"""
        try:
            from mpcontribs.client import Client as ContribsClient
            return ContribsClient(project=project_name, apikey=self.api_key)
        except ImportError:
            raise ImportError(
                "mpcontribs-client package required. Install with: pip install mpcontribs-client>=5.10.4"
            )
    
    def project_exists(self, project_name: str) -> bool:
        """
        Check if project exists in MPContribs.
        
        Args:
            project_name: Name of the project
            
        Returns:
            True if project exists, False otherwise
        """
        try:
            mpr = self._get_mprester()
            projects = mpr.contribs.get_projects()
            return project_name in [p.get('name') for p in projects]
        except Exception as e:
            logger.error(f"Error checking project existence: {e}")
            return False
    
    def create_project(
        self,
        name: str,
        title: str,
        authors: str,
        description: str,
        references: Optional[List[Dict[str, str]]] = None,
        dry_run: bool = False
    ) -> bool:
        """
        Create empty MPContribs project with metadata.
        
        Args:
            name: Project name (identifier)
            title: Project title
            authors: Comma-separated author names
            description: Project description
            references: Optional list of references [{"label": "...", "url": "..."}]
            dry_run: If True, only simulate the operation
            
        Returns:
            True if successful, False otherwise
        """
        if dry_run:
            logger.info(f"[DRY RUN] Would create MPContribs project: {name}")
            logger.info(f"  Title: {title}")
            logger.info(f"  Authors: {authors}")
            logger.info(f"  Description: {description[:100]}...")
            if references:
                logger.info(f"  References: {len(references)} links")
            return True
        
        try:
            mpr = self._get_mprester()
            
            # Check if project already exists
            if self.project_exists(name):
                logger.info(f"Project '{name}' already exists, updating instead")
                return self.update_project(name, title, authors, description, references)
            
            # Create project
            logger.info(f"Creating MPContribs project: {name}")
            mpr.contribs.create_project(
                name=name,
                title=title,
                authors=authors,
                description=description
            )
            
            # Add references if provided
            if references:
                client = self._get_client(name)
                client.update_project({"references": references})
                logger.info(f"  Added {len(references)} references")
            
            logger.info(f"✓ Successfully created project: {name}")
            logger.info(f"  View at: https://next-gen.materialsproject.org/contribs/projects/{name}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating project: {e}")
            return False
    
    def update_project(
        self,
        name: str,
        title: Optional[str] = None,
        authors: Optional[str] = None,
        description: Optional[str] = None,
        references: Optional[List[Dict[str, str]]] = None,
        dry_run: bool = False
    ) -> bool:
        """
        Update existing MPContribs project metadata.
        
        Args:
            name: Project name
            title: New title (optional)
            authors: New authors (optional)
            description: New description (optional)
            references: New references (optional)
            dry_run: If True, only simulate the operation
            
        Returns:
            True if successful, False otherwise
        """
        if dry_run:
            logger.info(f"[DRY RUN] Would update MPContribs project: {name}")
            if title:
                logger.info(f"  Title: {title}")
            if authors:
                logger.info(f"  Authors: {authors}")
            if description:
                logger.info(f"  Description: {description[:100]}...")
            if references:
                logger.info(f"  References: {len(references)} links")
            return True
        
        try:
            if not self.project_exists(name):
                logger.error(f"Project '{name}' does not exist. Create it first.")
                return False
            
            client = self._get_client(name)
            
            # Build update dict
            updates = {}
            if title:
                updates['title'] = title
            if authors:
                updates['authors'] = authors
            if description:
                updates['description'] = description
            if references:
                updates['references'] = references
            
            if not updates:
                logger.info("No updates to apply")
                return True
            
            logger.info(f"Updating MPContribs project: {name}")
            client.update_project(updates)
            logger.info(f"✓ Successfully updated project: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating project: {e}")
            return False
    
    def delete_project(self, name: str, dry_run: bool = False) -> bool:
        """
        Delete MPContribs project.
        
        Args:
            name: Project name
            dry_run: If True, only simulate the operation
            
        Returns:
            True if successful, False otherwise
        """
        if dry_run:
            logger.info(f"[DRY RUN] Would delete MPContribs project: {name}")
            return True
        
        try:
            if not self.project_exists(name):
                logger.warning(f"Project '{name}' does not exist")
                return False
            
            client = self._get_client(name)
            logger.warning(f"Deleting MPContribs project: {name}")
            client.delete_project()
            logger.info(f"✓ Successfully deleted project: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting project: {e}")
            return False


def setup_mpcontribs_project(
    product_config: Dict,
    dry_run: bool = False,
    api_key: Optional[str] = None
) -> bool:
    """
    Setup MPContribs project from product configuration.
    
    Args:
        product_config: Product configuration dict
        dry_run: If True, simulate the operation
        api_key: MP API key (optional)
        
    Returns:
        True if successful, False otherwise
    """
    manager = MPContribsProjectManager(api_key=api_key)
    
    # Extract metadata from product config
    name = product_config.get('name')
    metadata = product_config.get('metadata', {})
    
    title = metadata.get('title') or f"A-Lab {name.replace('_', ' ').title()}"
    authors = metadata.get('authors') or "A-Lab Team"
    description = metadata.get('description') or f"Automated synthesis data for {name}"
    
    # Build references list
    references = []
    if metadata.get('doi'):
        references.append({
            'label': 'doi',
            'url': f"https://doi.org/{metadata['doi']}"
        })
    
    # Add any additional references from config
    if metadata.get('references'):
        for ref in metadata['references']:
            if isinstance(ref, dict) and 'label' in ref and 'url' in ref:
                references.append(ref)
    
    # Always add S3 data location reference
    from config_loader import get_config
    config = get_config()
    s3_url = f"s3://{config.s3_bucket}/{config.s3_prefix}/{name}/"
    references.append({
        'label': 'data',
        'url': s3_url.replace('s3://', 'https://s3.amazonaws.com/')
    })
    
    # Create/update project
    return manager.create_project(
        name=name,
        title=title,
        authors=authors,
        description=description,
        references=references if references else None,
        dry_run=dry_run
    )


if __name__ == '__main__':
    # Test script
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python mpcontribs_setup.py <project_name> [--dry-run]")
        sys.exit(1)
    
    project_name = sys.argv[1]
    dry_run = '--dry-run' in sys.argv
    
    manager = MPContribsProjectManager()
    
    # Test project creation
    success = manager.create_project(
        name=project_name,
        title=f"Test Project {project_name}",
        authors="Test Author",
        description="Test description for MPContribs project",
        references=[
            {"label": "github", "url": "https://github.com/example/repo"}
        ],
        dry_run=dry_run
    )
    
    if success:
        print(f"✓ Project setup successful")
    else:
        print(f"✗ Project setup failed")
        sys.exit(1)

