import PyPDF2
import docx
import re
import json
import requests
from github import Github
from typing import Dict, List, Optional, Any
import logging
from io import BytesIO
import base64
from models.profile import Skill, Certification, GitHubProfile, ExtractedProfile, SkillLevel
from config.settings import settings

logger = logging.getLogger(__name__)

class ProfileExtractor:
    def __init__(self):
        self.github_client = Github(settings.github_token) if settings.github_token else None
        
        # Common skills patterns
        self.skill_patterns = {
            'programming_languages': [
                'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'ruby', 'php', 
                'go', 'rust', 'kotlin', 'swift', 'scala', 'r', 'matlab', 'perl', 'shell'
            ],
            'web_technologies': [
                'html', 'css', 'react', 'angular', 'vue', 'node.js', 'express', 'django', 
                'flask', 'fastapi', 'spring', 'laravel', 'jquery', 'bootstrap', 'tailwind'
            ],
            'databases': [
                'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch', 'cassandra',
                'oracle', 'sqlite', 'mariadb', 'neo4j', 'dynamodb'
            ],
            'cloud_platforms': [
                'aws', 'azure', 'gcp', 'google cloud', 'kubernetes', 'docker', 'terraform',
                'ansible', 'jenkins', 'gitlab', 'github actions'
            ],
            'data_science': [
                'machine learning', 'deep learning', 'tensorflow', 'pytorch', 'scikit-learn',
                'pandas', 'numpy', 'matplotlib', 'seaborn', 'jupyter', 'spark', 'hadoop'
            ]
        }
        
        # Certification patterns
        self.certification_patterns = [
            r'aws\s+certified',
            r'azure\s+certified',
            r'google\s+cloud\s+certified',
            r'certified\s+kubernetes',
            r'pmp\s+certified',
            r'cissp',
            r'comptia\s+\w+',
            r'oracle\s+certified',
            r'microsoft\s+certified',
            r'cisco\s+certified'
        ]
    
    def extract_from_resume(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Extract information from resume file"""
        try:
            text = ""
            
            if filename.lower().endswith('.pdf'):
                text = self._extract_from_pdf(file_content)
            elif filename.lower().endswith(('.doc', '.docx')):
                text = self._extract_from_docx(file_content)
            else:
                raise ValueError("Unsupported file format")
            
            return self._parse_resume_text(text)
            
        except Exception as e:
            logger.error(f"Failed to extract from resume: {e}")
            return {}
    
    def _extract_from_pdf(self, file_content: bytes) -> str:
        """Extract text from PDF"""
        try:
            pdf_file = BytesIO(file_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()
            return text
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            return ""
    
    def _extract_from_docx(self, file_content: bytes) -> str:
        """Extract text from DOCX"""
        try:
            doc_file = BytesIO(file_content)
            doc = docx.Document(doc_file)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            logger.error(f"DOCX extraction failed: {e}")
            return ""
    
    def _parse_resume_text(self, text: str) -> Dict[str, Any]:
        """Parse resume text and extract structured information"""
        text_lower = text.lower()
        
        # Extract skills
        skills = self._extract_skills(text_lower)
        
        # Extract certifications
        certifications = self._extract_certifications(text)
        
        # Extract experience years
        experience_years = self._extract_experience_years(text)
        
        # Extract education
        education = self._extract_education(text)
        
        # Extract contact info
        email = self._extract_email(text)
        phone = self._extract_phone(text)
        
        return {
            'skills': skills,
            'certifications': certifications,
            'experience_years': experience_years,
            'education': education,
            'contact': {
                'email': email,
                'phone': phone
            },
            'raw_text': text
        }
    
    def _extract_skills(self, text: str) -> List[Skill]:
        """Extract skills from text"""
        found_skills = []
        
        for category, skills_list in self.skill_patterns.items():
            for skill in skills_list:
                if skill in text:
                    # Determine skill level based on context
                    level = self._determine_skill_level(text, skill)
                    found_skills.append(Skill(
                        name=skill.title(),
                        level=level
                    ))
        
        return found_skills
    
    def _determine_skill_level(self, text: str, skill: str) -> SkillLevel:
        """Determine skill level based on context"""
        skill_context = text[max(0, text.find(skill) - 100):text.find(skill) + 100]
        
        if any(word in skill_context for word in ['expert', 'advanced', 'senior', 'lead']):
            return SkillLevel.EXPERT
        elif any(word in skill_context for word in ['proficient', 'experienced', 'intermediate']):
            return SkillLevel.ADVANCED
        elif any(word in skill_context for word in ['familiar', 'basic', 'beginner']):
            return SkillLevel.BEGINNER
        else:
            return SkillLevel.INTERMEDIATE
    
    def _extract_certifications(self, text: str) -> List[Certification]:
        """Extract certifications from text"""
        certifications = []
        
        for pattern in self.certification_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                cert_name = match.group().strip()
                certifications.append(Certification(
                    name=cert_name,
                    issuer="Unknown"
                ))
        
        return certifications
    
    def _extract_experience_years(self, text: str) -> Optional[int]:
        """Extract years of experience"""
        patterns = [
            r'(\d+)\+?\s*years?\s+(?:of\s+)?experience',
            r'experience\s*:?\s*(\d+)\+?\s*years?',
            r'(\d+)\+?\s*years?\s+in\s+\w+'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return None
    
    def _extract_education(self, text: str) -> List[str]:
        """Extract education information"""
        education = []
        degree_patterns = [
            r'bachelor\s+of\s+\w+',
            r'master\s+of\s+\w+',
            r'phd\s+in\s+\w+',
            r'b\.?tech\s+in\s+\w+',
            r'm\.?tech\s+in\s+\w+',
            r'mba\s+in\s+\w+'
        ]
        
        for pattern in degree_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                education.append(match.group().strip())
        
        return education
    
    def _extract_email(self, text: str) -> Optional[str]:
        """Extract email address"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, text)
        return match.group() if match else None
    
    def _extract_phone(self, text: str) -> Optional[str]:
        """Extract phone number"""
        phone_patterns = [
            r'\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            r'\b\d{10}\b'
        ]
        
        for pattern in phone_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group()
        
        return None
    
    def extract_from_github(self, github_url: str) -> Optional[GitHubProfile]:
        """Extract information from GitHub profile"""
        if not self.github_client:
            logger.warning("GitHub token not configured")
            return None
        
        try:
            # Extract username from URL
            username = github_url.split('/')[-1]
            user = self.github_client.get_user(username)
            
            # Get repositories
            repos = list(user.get_repos())
            repo_names = [repo.name for repo in repos[:10]]  # Limit to 10 repos
            
            # Get languages used
            languages = {}
            for repo in repos[:10]:
                try:
                    repo_languages = repo.get_languages()
                    for lang, lines in repo_languages.items():
                        languages[lang] = languages.get(lang, 0) + lines
                except:
                    continue
            
            return GitHubProfile(
                username=username,
                repositories=repo_names,
                languages=languages,
                contributions=0,  # GitHub API doesn't provide this easily
                followers=user.followers,
                following=user.following
            )
            
        except Exception as e:
            logger.error(f"Failed to extract GitHub data: {e}")
            return None
    
    def create_profile_summary(self, extracted_data: Dict[str, Any], github_data: Optional[GitHubProfile] = None) -> str:
        """Create human-readable profile summary"""
        summary_parts = []
        
        # Skills summary
        if 'skills' in extracted_data and extracted_data['skills']:
            skill_names = [skill.name for skill in extracted_data['skills']]
            summary_parts.append(f"Has skills in: {', '.join(skill_names[:10])}")
        
        # Experience
        if 'experience_years' in extracted_data and extracted_data['experience_years']:
            summary_parts.append(f"Has {extracted_data['experience_years']} years of experience")
        
        # Certifications
        if 'certifications' in extracted_data and extracted_data['certifications']:
            cert_names = [cert.name for cert in extracted_data['certifications']]
            summary_parts.append(f"Certified in: {', '.join(cert_names)}")
        
        # Education
        if 'education' in extracted_data and extracted_data['education']:
            summary_parts.append(f"Education: {', '.join(extracted_data['education'])}")
        
        # GitHub data
        if github_data:
            top_languages = sorted(github_data.languages.items(), key=lambda x: x[1], reverse=True)[:5]
            if top_languages:
                lang_names = [lang[0] for lang in top_languages]
                summary_parts.append(f"GitHub languages: {', '.join(lang_names)}")
        
        return ". ".join(summary_parts) + "."

# Global instance
profile_extractor = ProfileExtractor()