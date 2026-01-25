"""
RAG Data Model for PBS WARN Alerts

Defines the document schema and mapping logic for ingesting PBS WARN alerts
into the Chroma vector database.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from geopy.distance import geodesic

from mcp_server import now_utc_iso

logging.basicConfig(
    filename='pbs_warn_scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


@dataclass
class RAGDocument:
    """
    Structured representation of a PBS WARN alert for RAG indexing.
    
    Fields:
        id: Unique identifier (cap_identifier preferred)
        text: Combined searchable text (event + sender + message)
        event: Alert event type
        title: Alert title
        sender: Sender organization
        severity: Alert severity (Extreme, Severe, Moderate, Minor, Unknown)
        urgency: Alert urgency (Immediate, Expected, Future, Past, Unknown)
        certainty: Alert certainty (Observed, Likely, Possible, Unlikely, Unknown)
        status: Alert status (Actual, Test, Exercise, etc.)
        category: Alert category (Safety, Security, etc.)
        expires: Expiration timestamp (ISO format)
        sent: Sent timestamp (ISO format)
        cap_identifier: CAP message identifier
        areas: List of affected area dicts (stored as JSON string in metadata)
        latitude: Alert location latitude (if available)
        longitude: Alert location longitude (if available)
        source_file: Source JSON filename
        ingestion_timestamp: When document was ingested into RAG
    """
    id: str
    text: str
    event: Optional[str] = None
    title: Optional[str] = None
    sender: Optional[str] = None
    severity: Optional[str] = None
    urgency: Optional[str] = None
    certainty: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    expires: Optional[str] = None
    sent: Optional[str] = None
    cap_identifier: Optional[str] = None
    areas: Optional[List[Dict[str, Any]]] = None  # Keep as list for data, convert to JSON in metadata
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source_file: Optional[str] = None
    ingestion_timestamp: Optional[str] = None
    distance_to_central: Optional[float] = None
    processing_timestamp: Optional[str] = None
    
    # Class-level config for metadata generation
    _METADATA_EXCLUDE = {'id', 'text', 'areas'}  # Fields not to include in metadata (handled specially)
    _METADATA_DEFAULTS = {'latitude': 0.0, 'longitude': 0.0}  # Default values for metadata
    
    def to_chroma_format(self) -> tuple[str, Dict[str, Any], str]:
        """
        Convert to Chroma-compatible format using automatic metadata generation.
        
        Returns:
            Tuple of (document_text, metadata_dict, document_id)
        """
        # Start with automatic conversion from dataclass
        metadata = asdict(self)
        
        # Remove fields we don't want in metadata
        for field in self._METADATA_EXCLUDE:
            metadata.pop(field, None)
        
        # Apply defaults for missing values
        for field, default in self._METADATA_DEFAULTS.items():
            if metadata.get(field) is None:
                metadata[field] = default
        
        # Handle special cases
        if self.areas:
            metadata['areas'] = json.dumps(self.areas)  # Convert list to JSON string
        else:
            metadata['areas'] = ""
        
        # Ensure all values are strings or primitives (Chroma requirement)
        for key, value in metadata.items():
            if value is None:
                metadata[key] = ""
            elif isinstance(value, (int, float)):
                pass  # Keep as-is
            else:
                metadata[key] = str(value)
        
        return self.text, metadata, self.id


def map_alert_to_ragdoc(
    alert: Dict[str, Any],
    source_file: str = None,
    alert_index: int = 0
) -> RAGDocument:
    """
    Map a PBS WARN alert dict to a RAGDocument.
    
    Args:
        alert: Alert dictionary from PBS WARN API
        source_file: Source JSON filename
    
    Returns:
        RAGDocument instance
    """
    try:
        # Extract core fields (handle both raw and cleaned structures)
        event = alert.get('event') or alert.get('event_type') or alert.get('title', '')
        title = alert.get('title', '')
        sender = alert.get('sender', '')
        
        # Build searchable text: prioritize message content
        message = ''
        if 'message' in alert:
            message = alert['message']
        elif 'description' in alert:
            message = alert['description']
        elif 'texts' in alert and alert['texts']:
            # Concatenate all text values from raw API structure
            message = ' '.join(t.get('value', '') for t in alert['texts'] if t.get('value'))
        
        # Combine into searchable document text
        text_parts = []
        if event:
            text_parts.append(event)
        if sender:
            text_parts.append(f"from {sender}")
        if message:
            text_parts.append(f": {message}")

        # Fallback: if no event but we have message, start with message
        if not event and message:
            text = f"{sender}: {message}" if sender else message
        else:
            text = ' '.join(text_parts) if text_parts else f"Alert {alert.get('id', 'unknown')}"
        
        # Extract location (first available coordinates)
        latitude = alert.get('latitude')
        longitude = alert.get('longitude')
        
        # Extract geospatial metadata
        if 'areas' in alert:
            for area in alert['areas']:
                if area.get('type') == 'polygon' and 'coordinates' in area:
                    coords = area['coordinates'][0]  # Assuming first polygon
                    latitude = sum(pt[0] for pt in coords) / len(coords)
                    longitude = sum(pt[1] for pt in coords) / len(coords)
                    break

        # Calculate distance to a predefined location (e.g., central point)
        central_point = (33.4484, -112.0740)  # Example: Phoenix, AZ
        distance_to_central = None
        if latitude is not None and longitude is not None:
            distance_to_central = geodesic((latitude, longitude), central_point).miles

        # Generate unique ID (prefer cap_identifier, fallback to hash of alert content + index)
        cap_id = alert.get('cap_identifier') or alert.get('id')
        if cap_id:
            doc_id = str(cap_id)
        else:
            # Create hash-based ID from key alert fields + index + source to ensure uniqueness
            id_components = [
                alert.get('sender', ''),
                alert.get('event', ''),
                alert.get('sent', ''),
                alert.get('message', '')[:100],  # First 100 chars of message
                source_file or '',
                str(alert_index)  # Include index to differentiate identical alerts
            ]
            id_string = '|'.join(str(c) for c in id_components)
            doc_id = hashlib.md5(id_string.encode('utf-8')).hexdigest()[:16]  # 16-char hash
        
        # Current timestamp for ingestion tracking
        ingestion_ts = datetime.now(timezone.utc).isoformat() + 'Z'
        
        # Categorize alert based on severity, urgency, and event type
        severity = alert.get('severity', 'Unknown')
        urgency = alert.get('urgency', 'Unknown')
        event_type = alert.get('event', 'General')

        category = "Uncategorized"
        if severity == "Severe" and urgency in ["Immediate", "Expected"]:
            category = "High Priority"
        elif severity == "Moderate" or urgency == "Expected":
            category = "Moderate Priority"
        elif severity == "Minor" or urgency == "Future":
            category = "Low Priority"

        # Add processing timestamps
        processing_timestamp = now_utc_iso()

        # Map alert to RAGDocument
        return RAGDocument(
            id=doc_id,
            text=text,
            event=event,
            sender=sender,
            areas=alert.get('areas', []),
            latitude=latitude,
            longitude=longitude,
            source_file=source_file,
            ingestion_timestamp=processing_timestamp,
            category=category,
            distance_to_central=distance_to_central,
            processing_timestamp=processing_timestamp,
        )
        
    except Exception as e:
        logging.error(f"Error mapping alert to RAGDocument: {e}")
        raise


def batch_map_alerts(
    alerts: List[Dict[str, Any]],
    source_file: str = None
) -> List[RAGDocument]:
    """
    Map a list of alerts to RAGDocuments.
    
    Args:
        alerts: List of alert dicts
        source_file: Source JSON filename
    
    Returns:
        List of RAGDocument instances
    """
    docs = []
    for alert_index, alert in enumerate(alerts):
        try:
            doc = map_alert_to_ragdoc(alert, source_file, alert_index)
            docs.append(doc)
        except Exception as e:
            alert_id = alert.get('id', 'unknown')
            logging.warning(f"Skipping alert {alert_id} due to mapping error: {e}")
            continue
    
    logging.info(f"Mapped {len(docs)}/{len(alerts)} alerts to RAGDocuments")
    return docs