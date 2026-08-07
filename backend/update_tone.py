import sqlite3
import os

def update_tone_settings():
    db_path = os.path.join(os.path.dirname(__file__), "networking.db")
    print(f"Updating tone examples in database: {db_path}")
    
    if not os.path.exists(db_path):
        print("Database not found.")
        return

    # Seed tone_examples with a genericized style guide. Swap this out (or edit it from
    # the TwinAgent Profile screen in the app) with your own real examples — this is just
    # a structural starting point so the Message Writing Agent has a tone to imitate.
    successful_messages = """OUTREACH TONE GUIDE (EXAMPLE STRUCTURE):

1. Referral / Opportunity Inquiry:
"Hi [Name],
I'm [You], currently [Current Role] at [Current Company], where I work on [what you build]. I'm really impressed by your work at [Company], especially in [Team/Focus Area].
With my experience in [Relevant Skill], I believe I could contribute to your team's work. Are there any openings at [Company] that might fit my background?
I'd love to connect and learn more about potential opportunities!"

2. Connection Accepted / Advice Request:
"Hi [Name],
Thank you for accepting my connection request.
I spent some time going through your profile, and I was genuinely impressed by your journey to [Current Company]. That's exactly the kind of career path I aspire to build.
I'm currently [your status/goal]. If you ever have a few minutes, I'd be incredibly grateful for any advice you could share on [specific topic]."

3. Shared Background / Alumni Connection:
"Hi [Name],
Fellow [School/Community] here. I came across your profile while learning more about [Company] and really enjoyed your thoughts on [Insight/Topic].
I'm currently [your status], where I've been building [relevant project]. If you ever have a spare moment to share your perspective on [topic], I would truly value it."

4. Recruiter / Talent Advice Request:
"Hi [Name],
Thank you for connecting. I'm [your background/status].
I know you support technical recruiting at [Company], so I wanted to ask very humbly — what would you recommend candidates like me focus on to become stronger applicants?"

5. Thread Follow-up Tone Constraints:
- Keep thread follow-ups brief, conversational, and direct (usually 2 to 4 sentences).
- If the connection suggests other people or companies, thank them politely and leave the door open, without being pushy.
- Never repeat the first message's content; always add something new.
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
