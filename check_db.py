from database import SessionLocal
from models import MeetingUpdate

def check_updates():
    db = SessionLocal()
    try:
        results = db.query(MeetingUpdate).all()
        
        if not results:
            print("📅 Database is currently empty.")
            return

        print(f"{'ID':<4} | {'NAME':<15} | {'BATCH':<10} | {'UPDATE'}")
        print("-" * 80)
        
        for row in results:
            # 🛡️ Safety Check: If update is None, use an empty string
            content = row.update if row.update else "No update found"
            
            # Shorten for display
            display_text = (content[:47] + '..') if len(content) > 47 else content
            
            print(f"{row.id:<4} | {row.name:<15} | {row.batch_id:<10} | {display_text}")
            
    except Exception as e:
        print(f"❌ Error reading database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_updates()