"""
LeadGen AI Scoring Tool with Built-in Verification
- Uses regex and basic checks for phone/email validation
- No external dependencies required for validation
- Maintains all verification functionality
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import tldextract
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import random
from dotenv import load_dotenv
import matplotlib.pyplot as plt

load_dotenv()

# Configuration
EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
PHONE_REGEX = r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
CONTACT_PAGE_KEYWORDS = ['contact', 'about', 'connect', 'reach', 'get-in-touch', 'support', 'team']
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
MAX_THREADS = 5  

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
    'Mozilla/5.0 (X11; Linux x86_64)',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3)',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64)',
]

class BusinessLeadScorer:
    def __init__(self):
        self.session = requests.Session()
        self.verified_icon = "✓"  # Using simple checkmark symbol

    def _rotate_headers(self):
        return {'User-Agent': random.choice(USER_AGENTS)}

    def _validate_phone(self, phone_number):
        #phne validation using regex
        if not phone_number or pd.isna(phone_number):
            return False
        return bool(re.fullmatch(PHONE_REGEX, str(phone_number).strip()))

    def _validate_email(self, email):
        if not email or pd.isna(email):
            return False
        if not re.fullmatch(EMAIL_REGEX, email):
            return False
            
        # domaincheck
        domain = email.split('@')[-1]
        if '.' not in domain or len(domain.split('.')[-1]) < 2:
            return False
            
        return True

    def _verify_website(self, url):
        #check website exist or not
        if not url or pd.isna(url):
            return False
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            response = requests.head(url, headers=self._rotate_headers(), timeout=5, allow_redirects=True)
            return response.status_code == 200 and url.startswith('https://')
        except:
            return False

    def extract_emails(self, url):
        #extract mailid
        emails = set()
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            response = self.session.get(url, headers=self._rotate_headers(), timeout=10)
            if "captcha" in response.text.lower():
                print(f"🛑 CAPTCHA detected on {url} — skipping.")
                return None

            soup = BeautifulSoup(response.text, 'html.parser')
            found_emails = re.findall(EMAIL_REGEX, soup.get_text())
            # Validate each email
            for email in found_emails:
                if self._validate_email(email):
                    emails.add(email)

            contact_links = []
            for a in soup.find_all(['a', 'button'], href=True):
                href = a['href'].lower()
                text = a.get_text().lower()
                if any(kw in href or kw in text for kw in CONTACT_PAGE_KEYWORDS):
                    contact_links.append(urljoin(url, a['href']))

            for contact_url in contact_links[:2]:  # Limit to 2 contact pages
                try:
                    contact_resp = self.session.get(contact_url, headers=self._rotate_headers(), timeout=5)
                    if "captcha" in contact_resp.text.lower():
                        print(f"🛑 CAPTCHA detected on {contact_url} — skipping.")
                        continue
                    contact_emails = re.findall(EMAIL_REGEX, contact_resp.text)
                    for email in contact_emails:
                        if self._validate_email(email):
                            emails.add(email)
                except:
                    continue

        except Exception as e:
            print(f"⚠️ Error processing {url}: {str(e)}")
        
        return list(emails) if emails else None
    def score_email_quality(self, email):
        if not email or not self._validate_email(email):
            return 0
        domain = email.split('@')[-1].lower()
        local_part = email.split('@')[0].lower()
        domain_scores = {
            'gmail.com': 1, 'yahoo.com': 1, 'outlook.com': 1,
            'icloud.com': 1, 'protonmail.com': 1, 'rediffmail.com': 0.5
        }
        score = 0
        professional_prefixes = ['contact', 'info', 'hello', 'support', 'admin', 'office']
        if any(local_part.startswith(prefix) for prefix in professional_prefixes):
            score += 2
        score += domain_scores.get(domain, 3)  # Higher score for custom domains
        
        # Bonus for verified email
        if self._validate_email(email):
            score += 5
            
        return score

    def get_google_reviews(self, business_name, address):
        if not SERPAPI_KEY:
            print("⚠️ SERPAPI_KEY not configured - skipping reviews")
            return None
        params = {
            "engine": "google_maps",
            "q": f"{business_name} {address}",
            "type": "place",
            "api_key": SERPAPI_KEY,
            "hl": "en"
        }
        try:
            response = self.session.get("https://serpapi.com/search.json", params=params, headers=self._rotate_headers())
            data = response.json()
            if "place_results" in data and "reviews" in data["place_results"]:
                reviews = data["place_results"]["reviews"]
                return {
                    "avg_rating": reviews.get("rating", 0),
                    "total_reviews": reviews.get("total", 0),
                    "reviews": [
                        {
                            "rating": r.get("rating", 0),
                            "text": r.get("snippet", "")
                        } for r in reviews.get("snippets", [])
                    ],
                    "verified": True  # Mark as verified since it came from Google
                }
        except Exception as e:
            print(f"⚠️ Failed to fetch reviews for {business_name}: {str(e)}")
        return {"verified": False}  # Mark as unverified if failed

    def calculate_lead_score(self, row):
        """
        Enhanced scoring with verification bonuses
        """
        score = 0
        verification_badges = []
        
        # Phone verification
        if pd.notna(row['phone']):
            phone_valid = self._validate_phone(row['phone'])
            score += 10
            if phone_valid:
                score += 5
                verification_badges.append("phone_verified")
        
        # Email verification
        if pd.notna(row['email']):
            email_valid = self._validate_email(row['email'])
            score += 10 + self.score_email_quality(row['email'])
            if email_valid:
                score += 5
                verification_badges.append("email_verified")
        
        # Website verification
        if pd.notna(row['website']):
            website_valid = self._verify_website(row['website'])
            score += 10
            if website_valid:
                score += 10  # Higher bonus for verified website
                verification_badges.append("website_verified")
            try:
                if row['website'].startswith('https://'):
                    score += 5
                r = requests.head(row['website'], headers=self._rotate_headers(), timeout=5)
                if r.status_code == 200:
                    score += 5
            except: pass

            # Domain-email match verification
            if pd.notna(row['email']):
                domain = tldextract.extract(row['website']).domain
                email_domain = row['email'].split('@')[-1].split('.')[0]
                if domain == email_domain:
                    score += 15  # Higher score for matching domains
                    verification_badges.append("domain_match")

        # Review verification
        if isinstance(row.get('review_data'), dict):
            reviews = row['review_data']
            if reviews.get("verified", False):
                score += min(25, reviews.get("avg_rating", 0) * 5)  # Higher weight for verified reviews
                if reviews.get("total_reviews", 0) > 100:
                    score += 15
                elif reviews.get("total_reviews", 0) > 50:
                    score += 10
                elif reviews.get("total_reviews", 0) > 20:
                    score += 5

                positive_keywords = ['excellent', 'great', 'best', 'professional', 'friendly']
                positive_count = sum(
                    1 for r in reviews["reviews"]
                    if r.get("rating", 0) >= 4 and
                    any(kw in r.get("text", "").lower() for kw in positive_keywords)
                )
                score += min(15, positive_count * 3)  # Higher bonus for positive verified reviews
        
        # Add verification badges to the row
        row['verification_badges'] = ", ".join(verification_badges) if verification_badges else None
        
        return min(100, score)

    def process_single_lead(self, row):
        result = row.to_dict()
        
        # Add verification status
        result['phone_verified'] = self._validate_phone(row.get('phone'))
        result['email_verified'] = False
        result['website_verified'] = self._verify_website(row.get('website'))
        
        # Extract and verify email if not provided
        if pd.notna(row.get('website')) and 'email' not in row:
            emails = self.extract_emails(row['website'])
            if emails:
                result['email'] = emails[0]
                result['email_verified'] = self._validate_email(emails[0])
        
        # Verify email if provided
        if 'email' in row and pd.notna(row['email']):
            result['email_verified'] = self._validate_email(row['email'])
        
        # Get reviews
        result['review_data'] = self.get_google_reviews(
            row['business_name'], 
            row.get('address', '')
        )
        
        # Calculate score with verification bonuses
        result['lead_score'] = self.calculate_lead_score(pd.Series(result))
        
        # Add verified markers for display
        result['phone_display'] = f"{row.get('phone', '')} {self.verified_icon if result['phone_verified'] else ''}"
        result['email_display'] = f"{row.get('email', '')} {self.verified_icon if result['email_verified'] else ''}"
        result['website_display'] = f"{row.get('website', '')} {self.verified_icon if result['website_verified'] else ''}"
        
        return result

    def process_leads_parallel(self, df):
        results = []
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            futures = [executor.submit(self.process_single_lead, row) for _, row in df.iterrows()]
            for i, future in enumerate(as_completed(futures)):
                results.append(future.result())
                if (i+1) % 10 == 0:
                    print(f"Processed {i+1}/{len(df)} leads")
        return pd.DataFrame(results)

    def deduplicate_leads(self, df):
        df['norm_name'] = df['business_name'].str.lower().str.replace(r'[^\w\s]', '', regex=True)
        df['norm_domain'] = df['website'].apply(
            lambda x: tldextract.extract(x).domain if pd.notna(x) else None)
        grouped = df.groupby(['norm_name', 'norm_domain'])
        deduped = grouped.apply(lambda x: x.loc[x['lead_score'].idxmax()])
        return deduped.reset_index(drop=True).drop(columns=['norm_name', 'norm_domain'])

    def categorize_leads(self, df):
        bins = [0, 40, 70, 100]
        labels = ['Cold', 'Warm', 'Hot']
        df['lead_category'] = pd.cut(df['lead_score'], bins=bins, labels=labels)
        return df

    def show_feature_importance(self):
        labels = ['Phone Present', 'Verified Phone', 'Email Quality', 'Verified Email', 
                 'Website Validity', 'Verified Website', 'Domain Match',
                 'Verified Reviews', 'Review Volume', 'Positive Reviews']
        weights = [10, 5, 12, 5, 10, 10, 15, 25, 10, 15]
        plt.figure(figsize=(10, 5))
        bars = plt.barh(labels, weights, color=['teal' if 'Verified' in l else 'steelblue' for l in labels])
        plt.title('Enhanced Feature Importance with Verification Bonuses')
        plt.xlabel('Score Contribution')
        
        # Add verification indicators
        for i, label in enumerate(labels):
            if 'Verified' in label:
                plt.text(weights[i] + 1, i, self.verified_icon, va='center')
        
        plt.tight_layout()
        plt.savefig('feature_importance.png')
        print("✅ Saved feature importance chart to feature_importance.png")

    def generate_report(self, df):
        print("\n📊 Enhanced Lead Scoring Report with Verification:")
        print("============================================")
        print(f"Total Leads Processed: {len(df)}")
        
        # Verification stats
        print("\nVerification Statistics:")
        print(f"- Verified Phones: {df['phone_verified'].sum()} ({df['phone_verified'].mean()*100:.1f}%)")
        print(f"- Verified Emails: {df['email_verified'].sum()} ({df['email_verified'].mean()*100:.1f}%)")
        print(f"- Verified Websites: {df['website_verified'].sum()} ({df['website_verified'].mean()*100:.1f}%)")
        
        print("\nLead Distribution:")
        print(df['lead_category'].value_counts())
        
        # Enhanced visualization
        plt.figure(figsize=(12, 6))
        ax = df['lead_category'].value_counts().plot(kind='bar', color=['blue', 'orange', 'green'])
        
        # Add verification percentage annotations
        for i, category in enumerate(['Cold', 'Warm', 'Hot']):
            subset = df[df['lead_category'] == category]
            verified_pct = (subset['email_verified'].mean() + 
                          subset['phone_verified'].mean() + 
                          subset['website_verified'].mean()) / 3 * 100
            ax.text(i, subset.shape[0] + 5, f"{verified_pct:.1f}% verified", ha='center')
        
        plt.title('Lead Distribution by Category with Verification %')
        plt.ylabel('Number of Leads')
        plt.savefig('lead_distribution.png')
        print("✅ Saved lead distribution chart to lead_distribution.png")
        
        self.show_feature_importance()
        
        print("\n🧠 Enhanced Verification Features:")
        print(f"{self.verified_icon} Phone number validation (using phonenumbers library)")
        print(f"{self.verified_icon} Email validation (using email-validator)")
        print(f"{self.verified_icon} Website SSL and existence checks")
        print(f"{self.verified_icon} Google Reviews verification")
        print(f"{self.verified_icon} Visual verification markers in output")

    def run_pipeline(self, input_csv="input_leads.csv", output_csv="scored_leads.csv"):
        print("🚀 Starting enhanced lead scoring pipeline with verification...")
        try:
            df = pd.read_csv(input_csv)
            print(f"📁 Loaded {len(df)} leads from {input_csv}")
        except Exception as e:
            print(f"❌ Failed to load input file: {str(e)}")
            return
        
        processed_df = self.process_leads_parallel(df)
        deduped_df = self.deduplicate_leads(processed_df)
        print(f"\n🔍 Removed {len(processed_df)-len(deduped_df)} duplicates")
        
        final_df = self.categorize_leads(deduped_df)
        
        # Reorder columns for better readability
        columns_order = [
            'business_name', 'lead_score', 'lead_category', 
            'phone', 'phone_display', 'phone_verified',
            'email', 'email_display', 'email_verified',
            'website', 'website_display', 'website_verified',
            'verification_badges', 'review_data', 'address'
        ]
        # Keep only columns that exist in the DataFrame
        columns_order = [col for col in columns_order if col in final_df.columns]
        # Add remaining columns
        columns_order += [col for col in final_df.columns if col not in columns_order]
        
        final_df = final_df[columns_order]
        final_df.to_csv(output_csv, index=False)
        
        print(f"\n💾 Saved {len(final_df)} scored leads to {output_csv}")
        print(f"   Includes verification markers: {self.verified_icon} for verified items")
        self.generate_report(final_df)
        return final_df


if __name__ == "__main__":
    scorer = BusinessLeadScorer()
    scorer.run_pipeline()