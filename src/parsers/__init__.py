import importlib
import logging

logger = logging.getLogger("ParserLoader")

def load_parser(domain):
    """
    Dynamically imports a parser module based on the domain name.
    Example: 'startech.com.bd' -> tries to import 'src.parsers.startech'
    """
    # Clean domain to get a valid filename (e.g., startech.com.bd -> startech)
    # This assumes your filenames match the main part of the domain.
    module_name = domain.split('.')[0]
    
    try:
        # Import the module dynamically
        module = importlib.import_module(f"parsers.{module_name}")
        
        # Check if it has the required 'parse' function
        if hasattr(module, "parse"):
            logger.info(f"✅ Successfully loaded parser for {domain}")
            return module.parse
        else:
            logger.error(f"❌ Module 'parsers.{module_name}' exists but has no 'parse' function.")
            return None
            
    except ImportError:
        logger.error(f"❌ No parser file found for domain: {domain} (Expected: src/parsers/{module_name}.py)")
        return None