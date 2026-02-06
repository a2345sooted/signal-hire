import io

from reportlab.lib.pagesizes import LETTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


class PDFGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        # Header Style
        self.styles.add(ParagraphStyle(
            name='ResumeHeader',
            fontSize=18,
            leading=22,
            alignment=1,  # Center
            spaceAfter=6,
            fontName='Helvetica-Bold'
        ))
        
        # Subtitle Style
        self.styles.add(ParagraphStyle(
            name='ResumeSubtitle',
            fontSize=10,
            leading=12,
            alignment=1,  # Center
            spaceAfter=12,
            fontName='Helvetica'
        ))

        # Section Heading Style
        self.styles.add(ParagraphStyle(
            name='SectionHeading',
            fontSize=14,
            leading=18,
            spaceBefore=12,
            spaceAfter=6,
            fontName='Helvetica-Bold',
            borderPadding=(0, 0, 2, 0),
            borderWidth=0,
            borderColor=None
        ))

        # Job Title Style
        self.styles.add(ParagraphStyle(
            name='JobTitle',
            fontSize=11,
            leading=13,
            fontName='Helvetica-Bold'
        ))

        # Date Style
        self.styles.add(ParagraphStyle(
            name='DateStyle',
            fontSize=10,
            leading=12,
            fontName='Helvetica-Oblique',
            alignment=2 # Right alignment if needed, but we'll use tables or just flow
        ))

    def generate_pdf(self, resume_data: dict) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=LETTER,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )

        elements = []

        # 1. Contact Info
        contact = resume_data.get("contact", {})
        if contact.get("name"):
            elements.append(Paragraph(contact["name"], self.styles['ResumeHeader']))
        
        contact_parts = []
        if contact.get("email"): contact_parts.append(contact["email"])
        if contact.get("phone"): contact_parts.append(contact["phone"])
        if contact.get("location"): contact_parts.append(contact["location"])
        if contact.get("linkedin"): contact_parts.append(contact["linkedin"])
        
        if contact_parts:
            elements.append(Paragraph(" | ".join(contact_parts), self.styles['ResumeSubtitle']))

        # 2. Summary
        if resume_data.get("summary"):
            elements.append(Paragraph("PROFESSIONAL SUMMARY", self.styles['SectionHeading']))
            elements.append(Paragraph(resume_data["summary"], self.styles['Normal']))

        # 3. Experience
        if resume_data.get("experience"):
            elements.append(Paragraph("PROFESSIONAL EXPERIENCE", self.styles['SectionHeading']))
            for exp in resume_data["experience"]:
                title_company = f"<b>{exp.get('title', '')}</b>"
                if exp.get('company'):
                    title_company += f" | {exp.get('company')}"
                
                elements.append(Paragraph(title_company, self.styles['Normal']))
                
                if exp.get('dates'):
                    elements.append(Paragraph(exp['dates'], self.styles['DateStyle']))
                
                bullets = exp.get("bullets", [])
                if bullets:
                    list_items = [ListItem(Paragraph(bullet, self.styles['Normal'])) for bullet in bullets]
                    elements.append(ListFlowable(list_items, bulletType='bullet', leftIndent=20))
                
                elements.append(Spacer(1, 6))

        # 4. Projects
        projects = resume_data.get("projects", [])
        ai_projects = resume_data.get("ai_projects", [])
        all_projects = projects + ai_projects
        
        if all_projects:
            elements.append(Paragraph("PROJECTS", self.styles['SectionHeading']))
            for proj in all_projects:
                proj_name = f"<b>{proj.get('name', '')}</b>"
                if proj.get('technologies'):
                    proj_name += f" ({', '.join(proj['technologies'])})"
                
                elements.append(Paragraph(proj_name, self.styles['Normal']))
                
                if proj.get('description'):
                    elements.append(Paragraph(proj['description'], self.styles['Normal']))
                
                for link in proj.get('links', []):
                    elements.append(Paragraph(f"Link: {link}", self.styles['Normal']))
                
                elements.append(Spacer(1, 4))

        # 5. Skills
        if resume_data.get("skills"):
            elements.append(Paragraph("SKILLS", self.styles['SectionHeading']))
            elements.append(Paragraph(", ".join(resume_data["skills"]), self.styles['Normal']))

        # 6. Education
        if resume_data.get("education"):
            elements.append(Paragraph("EDUCATION", self.styles['SectionHeading']))
            for edu in resume_data["education"]:
                edu_line = f"<b>{edu.get('degree', '')}</b>"
                if edu.get('school'):
                    edu_line += f", {edu['school']}"
                if edu.get('dates'):
                    edu_line += f" ({edu['dates']})"
                
                elements.append(Paragraph(edu_line, self.styles['Normal']))

        # 7. Military Service
        if resume_data.get("military_service"):
            elements.append(Paragraph("MILITARY SERVICE", self.styles['SectionHeading']))
            elements.append(Paragraph(resume_data["military_service"], self.styles['Normal']))

        # 8. Interests
        if resume_data.get("interests"):
            elements.append(Paragraph("INTERESTS & CERTIFICATIONS", self.styles['SectionHeading']))
            elements.append(Paragraph(", ".join(resume_data["interests"]), self.styles['Normal']))

        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes


class PDFGeneratorService(PDFGenerator):
    pass
