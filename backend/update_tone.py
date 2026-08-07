import sqlite3
import os

def update_tone_settings():
    db_path = os.path.join(os.path.dirname(__file__), "networking.db")
    print(f"Updating tone examples in database: {db_path}")
    
    if not os.path.exists(db_path):
        print("Database not found.")
        return

    # Formulate Rishindra's expanded successful messages and strategies
    successful_messages = """RISHINDRA'S SUCCESSFUL OUTREACH TEMPLATES & NETWORKING STRATEGIES:

1. Target Referral / Opportunity Hook (e.g., Yujuan - Google Core ML):
"Hi [Name],
Hope you're doing well! I'm Rishindra, currently an AI Engineer Intern at ZUZU, where I work on building an AI-powered onboarding platform. I'm really impressed by your work at [Company], especially in the [Team/Focus Area] with your focus on [Specific NLP/ML Tech].
With my experience in FastAPI and a strong background in data analysis, I believe I could contribute to your team’s innovative projects. Are there any openings at [Company] that might fit my background in AI and software engineering?
I'd love to connect and learn more about potential opportunities!"

2. Connection Accepted Follow-up / Advice Request (e.g., Zachary - Runway):
"Hi [Name],
Thank you for accepting my connection request. I really appreciate it.
I spent some time going through your profile, and I was genuinely impressed by your journey. From [Previous Company] to [Next Company] and now [Current Company], it feels like every move was intentional and helped you build deeper expertise in [Subject Domain]. That's exactly the kind of career path I aspire to build.
I'm currently pursuing my Master's in Computer Science and working as an AI Engineer Intern. My long term goal is to build impactful AI products and become a strong software engineer. The market has been challenging, so I'm trying to learn from people who have already navigated this path successfully.
If you ever have a few minutes, I'd be incredibly grateful for any advice you could share. Whether it's resume improvements, interview preparation, networking, career decisions, or the kinds of AI projects that helped you stand out, I would truly value your perspective."

3. Wright State University Alumni Connection (e.g., Matt - Rokt):
"Fellow Wright State Builder 👋
Hi [Name],
Fellow Wright State alum here. I came across your profile while learning more about [Company] and really enjoyed your thoughts on [Insight/Topic].
I recently completed the [Stage/Interview] for the [Role] and wanted to reach out. I'm currently pursuing my MS in CS at Wright State and working as an AI Engineer Intern at ZUZU.AI, where I've been building RAG systems and agent-based workflows. Outside of work, I enjoy building side projects ranging from multi-agent systems to an IEEE-published computer vision project."

4. Recruiter / TA Specialist Advice Request (e.g., Micah - Google TA):
"Hi [Name],
Thank you for connecting. I'm a CS Master's student at Wright State University working on AI/ML projects, including an IEEE-published paper and the Google x Kaggle AI Agents Intensive.
I know you support technical recruiting at [Company], so I wanted to ask very humbly — what would you recommend students like me focus on to become stronger candidates in the future?
I’d truly appreciate even a small piece of advice."

5. Responding to Creators/Influencer Inquiries (e.g., Seth Forbes):
"Hi [Name],
Thanks for reaching out - glad to connect.
What drew me to your profile was your focus on communicating insights clearly and building business context, especially for early-career professionals. Coming from a computer science background, I've been realizing how important it is to translate technical work into decisions that stakeholders can actually act on, which resonated with me.
I'm currently a graduate student in computer science, so I'm still early in my career and very much in the learning phase. Looking forward to learning from your content and perspectives."

6. Handling Citizenship & Government Clearance Mandates (e.g., Matt Grafflin):
"Hi [Name],
Thank you so much for the thoughtful and transparent reply - I genuinely appreciate you taking the time to explain everything clearly. I completely understand the security clearance and citizenship requirements, and I appreciate your honesty.
If your network has any leads or companies that might be a better fit for someone early in their software/data/ML career, I would be truly grateful for an introduction."

7. Visa & Sponsorship Q&A Guidelines:
- In official applications, answer 'Yes' to 'Eligible to work now?' (due to CPT/OPT) and 'Yes' to 'Will you require sponsorship in the future?' (due to future H-1B needs).
- On internship applications, when faced with extreme auto-rejection risk due to sponsor filters, you may select 'No' to sponsorship for the duration of the internship with the goal of explaining your CPT/OPT authorization during subsequent recruiter calls.
- Defer all generation to focus on technical alignment, project metrics, and timeline co-op availability.

8. Thread Follow-up Tone Constraints:
- Keep thread follow-ups brief, conversational, and direct (usually 2 to 4 sentences).
- If the connection suggests other companies, thank them politely and open the door for referrals or intros.
"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if tone_examples key exists for each user
    cursor.execute("SELECT id FROM users")
    users = cursor.fetchall()
    
    for (user_id,) in users:
        cursor.execute("SELECT id FROM settings WHERE user_id = ? AND key = 'tone_examples'", (user_id,))
        record = cursor.fetchone()
        if record:
            cursor.execute("UPDATE settings SET value = ? WHERE user_id = ? AND key = 'tone_examples'", (successful_messages, user_id))
        else:
            cursor.execute("INSERT INTO settings (user_id, key, value) VALUES (?, 'tone_examples', ?)", (user_id, 'tone_examples', successful_messages))
        print(f"Updated tone_examples setting for user ID: {user_id}")
        
    conn.commit()
    conn.close()
    print("Database tone updates complete.")

if __name__ == "__main__":
    update_tone_settings()
