import os
from dotenv import load_dotenv

# Load database config from .env if present
load_dotenv()

from app.database.connection import session_scope
from app.models.db_models import QualificationMaster, QualificationAlias

def seed_qualifications():
    print("Starting Seeding Qualification Master and Alises...")
    
    data = {
        "btech": ["btech", "be", "b tech", "b e", "bachelor of technology", "bachelor of engineering"],
        "mtech": ["mtech", "m tech", "master of technology"],
        "me": ["me", "m e", "master of engineering"],
        "mba": ["mba", "master of business administration"],
        "bca": ["bca", "bachelor of computer applications"],
        "mca": ["mca", "master of computer applications"],
        "bsc": ["bsc", "b sc", "bachelor of science"],
        "msc": ["msc", "m sc", "master of science"],
    }
    
    with session_scope() as session:
        for generic_key, aliases in data.items():
            # Create Master
            master = session.get(QualificationMaster, generic_key)
            if not master:
                master = QualificationMaster(generic_key=generic_key, category="Education")
                session.add(master)
                session.flush()
            
            # Add Aliases
            for alias in aliases:
                # Check if alias already exists
                existing = session.query(QualificationAlias).filter_by(
                    generic_key=generic_key, alias_value=alias.lower().strip()
                ).first()
                
                if not existing:
                    new_alias = QualificationAlias(generic_key=generic_key, alias_value=alias.lower().strip())
                    session.add(new_alias)
        
        session.commit()
    print("Done. Seeding completed!")

if __name__ == "__main__":
    seed_qualifications()
