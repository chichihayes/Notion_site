import streamlit as st
import requests
import json
import re

# API keys from Streamlit secrets
JINA_API_KEY = st.secrets["JINA_API_KEY"]
OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
DEFAULT_NOTION_URL = "https://techbrews.notion.site/Welcome-to-Tech-Brews-a9805827439d46f3b9d60a10bf39ebda"

MAX_LINKS_TO_FOLLOW = 5

class NotionPageReader:
    def __init__(self, jina_key, openrouter_key):
        self.jina_key = jina_key
        self.openrouter_key = openrouter_key
        self.visited_urls = set()
        self.page_contents = {}
        
    def extract_page_content(self, url):
        """Extract actual page content using Jina AI Reader"""
        if url in self.visited_urls:
            return self.page_contents.get(url, "")
        
        try:
            # Use Jina AI Reader to fetch actual page content
            response = requests.get(
                f"https://r.jina.ai/{url}",
                headers={
                    'Authorization': f'Bearer {self.jina_key}',
                    'X-Return-Format': 'text'  # Get clean text output
                },
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.text
                
                # Clean up the content - remove excessive whitespace
                content = re.sub(r'\n{3,}', '\n\n', content)
                
                self.visited_urls.add(url)
                self.page_contents[url] = content
                return content
            else:
                st.warning(f"Failed to fetch {url}: Status {response.status_code}")
                return ""
                
        except Exception as e:
            st.error(f"Error extracting content from {url}: {str(e)}")
            return ""
    
    def extract_notion_links(self, text):
        """Extract Notion links from text"""
        pattern = r'https://(?:www\.)?notion\.(?:site|so)/[^\s\)"\']+'
        return list(set(re.findall(pattern, text)))
    
    def ask_llm_for_links(self, question, main_content, available_links):
        """Ask LLM to select most relevant links to follow"""
        if not available_links:
            return []
        
        prompt = f"""Given this question: "{question}"

Available links from the page:
{chr(10).join([f"- {link}" for link in available_links[:20]])}

Return ONLY a JSON array of the 3 most relevant URLs that would help answer this question: ["url1", "url2", "url3"]
If none are relevant, return: []"""

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/techbrews",
                    "X-Title": "TechBrews Assistant"
                },
                json={
                    "model": "google/gemini-2.5-flash-lite",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                },
                timeout=30
            )
            
            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content'].strip()
                # Extract JSON from response
                if '[' in content and ']' in content:
                    json_start = content.index('[')
                    json_end = content.rindex(']') + 1
                    json_str = content[json_start:json_end]
                    return json.loads(json_str)[:MAX_LINKS_TO_FOLLOW]
            return []
                
        except Exception as e:
            st.warning(f"Error selecting links: {str(e)}")
            return []
    
    def answer_question(self, question, url, follow_links=True):
        """Main function to answer questions about Notion pages"""
        with st.spinner("Reading main page..."):
            main_content = self.extract_page_content(url)
        
        if not main_content:
            return "❌ Couldn't extract content from the page. The page might be private or blocked."
        
        # Build context starting with main page
        all_content = f"=== Main Page ({url}) ===\n{main_content}\n"
        
        if follow_links:
            # Extract links from the main page
            links = self.extract_notion_links(main_content)
            
            if links:
                st.info(f"Found {len(links)} linked pages. Analyzing relevance...")
                
                # Ask LLM which links are relevant
                relevant_links = self.ask_llm_for_links(question, main_content, links)
                
                if relevant_links:
                    st.info(f"Following {len(relevant_links)} relevant pages...")
                    
                    # Fetch content from relevant links
                    for i, link in enumerate(relevant_links, 1):
                        with st.spinner(f"Reading linked page {i}/{len(relevant_links)}..."):
                            link_content = self.extract_page_content(link)
                            if link_content:
                                all_content += f"\n\n=== Linked Page: {link} ===\n{link_content}\n"
        
        # Generate answer using all collected content
        with st.spinner("Generating answer..."):
            return self.generate_answer(question, all_content)
    
    def generate_answer(self, question, context):
        """Generate answer using LLM based on extracted content"""
        prompt = f"""You are a helpful assistant answering questions about Tech Brews community based on their Notion pages.

Question: "{question}"

Content from Notion pages:
{context[:15000]}  

Instructions:
- Provide a clear, accurate answer based ONLY on the content above
- If the content doesn't contain the answer, say so
- Include relevant details and examples
- Keep the answer concise but complete
- Use a friendly, professional tone"""

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/techbrews",
                    "X-Title": "TechBrews Assistant"
                },
                json={
                    "model": "google/gemini-2.5-flash-lite",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 1000
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            
            error_msg = f"API Error {response.status_code}"
            try:
                error_detail = response.json()
                if 'error' in error_detail:
                    error_msg += f": {error_detail['error'].get('message', '')}"
            except:
                pass
            return f"❌ {error_msg}"
                
        except Exception as e:
            return f"❌ Error generating answer: {str(e)}"


def main():
    st.set_page_config(
        page_title="Tech Brews Assistant",
        page_icon="☕",
        layout="wide"
    )
    
    st.title("☕ Tech Brews Assistant")
    st.markdown("Ask questions about the Tech Brews community - now with **real page content**!")
    
    # Initialize reader
    reader = NotionPageReader(JINA_API_KEY, OPENROUTER_API_KEY)
    
    # Layout
    col1, col2 = st.columns([3, 1])
    
    with col1:
        question = st.text_input(
            "Your question:",
            placeholder="What is Tech Brews all about?",
        )
    
    with col2:
        follow_links = st.checkbox("Follow links", value=True, 
                                   help="Automatically follow relevant links on the page")
    
    # Process question
    if question:
        answer = reader.answer_question(question, DEFAULT_NOTION_URL, follow_links)
        
        st.markdown("### Answer")
        st.markdown(answer)
        
        # Show sources
        if reader.visited_urls:
            with st.expander(f"📚 Sources ({len(reader.visited_urls)} pages read)"):
                for url in reader.visited_urls:
                    st.markdown(f"- {url}")
    
    # Info section
    with st.expander("ℹ️ How it works"):
        st.markdown("""
        This assistant uses **Jina AI Reader** to extract actual content from Notion pages:
        
        1. 📖 Reads the main Notion page content
        2. 🔍 Finds all linked Notion pages
        3. 🤖 Uses AI to select the most relevant links for your question
        4. 📚 Reads those linked pages too
        5. ✨ Generates a comprehensive answer based on all content
        
        **Note:** The assistant can only read public Notion pages.
        """)


if __name__ == "__main__":
    main()
