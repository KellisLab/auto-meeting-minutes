from django.db import models
from django.contrib.postgres.fields import ArrayField
import uuid


class Member(models.Model):
    """Represents a person in the organization."""

    name = models.CharField(max_length=200)
    active = models.BooleanField(default=True)
    
    # Store multiple values as comma-separated strings
    emails = models.TextField(blank=True, help_text="Comma-separated email addresses")
    github_usernames = models.TextField(blank=True, help_text="Comma-separated GitHub usernames")
    phone_numbers = models.TextField(blank=True, help_text="Comma-separated phone numbers")
    discord_usernames = models.TextField(blank=True, help_text="Comma-separated Discord usernames")
    teams = models.TextField(blank=True, help_text="Comma-separated team names")
    
    # Technical skills
    skills = ArrayField(
        models.CharField(max_length=100),
        blank=True,
        default=list,
        help_text="Technical skills and expertise",
    )
    
    # Onboarding form fields
    form_status = models.CharField(max_length=100, blank=True, help_text="Status from onboarding form")
    summer_commitment = models.CharField(max_length=500, blank=True, help_text="Summer 2025 commitment level")
    role = models.CharField(max_length=200, blank=True, help_text="Current role in the organization")
    whatsapp_number = models.CharField(max_length=100, blank=True, help_text="WhatsApp mobile number")
    github_email = models.EmailField(blank=True, help_text="GitHub email address")
    website = models.URLField(blank=True, help_text="Personal website URL")

    contribution_hours = models.TextField(blank=True, help_text="Expected contribution hours and period")
    time_constraints = models.TextField(blank=True, help_text="Time constraints and availability")
    top_accomplishments = models.TextField(blank=True, help_text="Top accomplishments listed")
    career_education_status = models.TextField(blank=True, help_text="Current career/education status")
    coding_experience = models.TextField(blank=True, help_text="Coding experience description")
    application_areas = models.TextField(blank=True, help_text="Application areas of interest")
    platform_contributions = models.TextField(blank=True, help_text="Proposed contributions to platform")
    vertical_contributions = models.TextField(blank=True, help_text="Proposed contributions to verticals")
    ideal_role = models.TextField(blank=True, help_text="Ideal role if all goes well")
    additional_info = models.TextField(blank=True, help_text="Additional info, comments, questions")
    proposed_roles = ArrayField(
        models.CharField(max_length=200),
        blank=True,
        default=list,
        help_text="Proposed roles in Mantis team",
    )
    onboarding_timestamp = models.DateTimeField(null=True, blank=True, help_text="Timestamp from onboarding form submission")

    def __str__(self):
        return self.name
    
    # Helper methods to work with the comma-separated values
    def get_emails_list(self):
        """Returns emails as a list."""
        return [email.strip() for email in self.emails.split(',') if email.strip()]
    
    def get_github_usernames_list(self):
        """Returns GitHub usernames as a list."""
        return [username.strip() for username in self.github_usernames.split(',') if username.strip()]
    
    def get_phone_numbers_list(self):
        """Returns phone numbers as a list."""
        return [phone.strip() for phone in self.phone_numbers.split(',') if phone.strip()]
    
    def get_discord_usernames_list(self):
        """Returns Discord usernames as a list."""
        return [username.strip() for username in self.discord_usernames.split(',') if username.strip()]
    
    def get_teams_list(self):
        """Returns teams as a list."""
        return [team.strip() for team in self.teams.split(',') if team.strip()]
    
    # Helper methods to set values from lists
    def set_emails_from_list(self, email_list):
        """Sets emails from a list."""
        self.emails = ', '.join(email_list)
    
    def set_github_usernames_from_list(self, username_list):
        """Sets GitHub usernames from a list."""
        self.github_usernames = ', '.join(username_list)
    
    def set_phone_numbers_from_list(self, phone_list):
        """Sets phone numbers from a list."""
        self.phone_numbers = ', '.join(phone_list)
    
    def set_discord_usernames_from_list(self, username_list):
        """Sets Discord usernames from a list."""
        self.discord_usernames = ', '.join(username_list)
    
    def set_teams_from_list(self, team_list):
        """Sets teams from a list."""
        self.teams = ', '.join(team_list)
    
    def get_skills_list(self):
        """Returns skills as a list."""
        return self.skills if self.skills else []
    
    def set_skills_from_list(self, skills_list):
        """Sets skills from a list."""
        self.skills = skills_list if skills_list else []
    
    def get_proposed_roles_list(self):
        """Returns proposed roles as a list."""
        return self.proposed_roles if self.proposed_roles else []
    
    def set_proposed_roles_from_list(self, roles_list):
        """Sets proposed roles from a list."""
        self.proposed_roles = roles_list if roles_list else []


class Project(models.Model):
    """Represents a GitHub repository or project."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    github_repo_url = models.URLField(blank=True, help_text="GitHub repository URL")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Link to team members working on this project
    members = models.ManyToManyField(Member, blank=True, related_name='projects')
    
    def __str__(self):
        return self.name


class Issue(models.Model):
    """Pipeline for storing GitHub issues with foreign key to Member for team visualization."""
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('in_progress', 'In Progress'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Core issue data
    title = models.CharField(max_length=500)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    
    # GitHub integration
    github_issue_number = models.IntegerField()
    github_issue_url = models.URLField()
    github_project = models.CharField(max_length=200, blank=True, help_text="GitHub project/team name")
    github_repository = models.CharField(max_length=200, blank=True, help_text="GitHub repository name (e.g., Mantis, MantisAPI)")
    
    # Foreign key relationships
    assignee = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, 
                                related_name='assigned_issues')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='issues')
    
    # Timestamps
    github_created_at = models.DateTimeField()
    github_updated_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        assignee_name = self.assignee.name if self.assignee else "Unassigned"
        return f"#{self.github_issue_number}: {self.title[:50]} ({assignee_name})"
    
    @property
    def repository_name(self):
        """Extract repository name from project's GitHub URL."""
        if self.project and self.project.github_repo_url:
            return self.project.github_repo_url.rstrip('/').split('/')[-1]
        return self.project.name if self.project else "Unknown"
    
    class Meta:
        unique_together = ['github_issue_number', 'project']


class Meeting(models.Model):
    """Represents a meeting processed from Panopto."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500)
    panopto_id = models.CharField(max_length=100, unique=True, help_text="Panopto video ID")
    panopto_url = models.URLField(help_text="Original Panopto URL")
    meeting_date = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(null=True, blank=True)
    team_name = models.CharField(max_length=100, blank=True, null=True, help_text="Extracted team name from meeting title")
    meeting_type = models.CharField(max_length=100, blank=True, null=True, help_text="Extracted meeting type (e.g., AllHands, Standup, Review)")
    
    # Processing metadata
    processed_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    transcript_file_path = models.TextField(blank=True, help_text="Path to original transcript file")
    
    def __str__(self):
        return f"{self.title} ({self.meeting_date.strftime('%Y-%m-%d') if self.meeting_date else 'No date'})"

    class Meta:
        ordering = ['-meeting_date', '-processed_at']


class MeetingTranscript(models.Model):
    """Represents a transcript segment from a meeting, linked to a speaker (Member)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='transcripts')
    speaker = models.ForeignKey(Member, on_delete=models.SET_NULL, null=True, blank=True, 
                               related_name='meeting_transcripts')
    
    # Transcript content
    speaker_name = models.CharField(max_length=200, help_text="Original speaker name from transcript")
    content = models.TextField(help_text="Transcript content for this speaker")
    
    # Timing information
    start_time = models.CharField(max_length=20, blank=True, help_text="Start timestamp (HH:MM:SS)")
    end_time = models.CharField(max_length=20, blank=True, help_text="End timestamp (HH:MM:SS)")
    
    # AI-generated summary (optional)
    summary = models.TextField(blank=True, help_text="AI-generated summary of this speaker's content")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        speaker_display = self.speaker.name if self.speaker else self.speaker_name
        return f"{self.meeting.title} - {speaker_display} ({self.start_time})"
    
    class Meta:
        ordering = ['meeting', 'start_time']


class DiscordTranscript(models.Model):
    """Represents a conversation transcript from Discord channels."""

    CHANNEL_TYPE_CHOICES = [
        ('text', 'Text Channel'),
        ('voice', 'Voice Channel'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Discord channel information
    channel_name = models.CharField(max_length=200, help_text="Name of the Discord channel")
    channel_type = models.CharField(max_length=10, choices=CHANNEL_TYPE_CHOICES, help_text="Type of Discord channel")
    channel_id = models.CharField(max_length=100, help_text="Discord channel ID")
    
    # Conversation content
    description = models.TextField(help_text="Summary/description of the conversation")
    
    # Timing information
    timestamp = models.DateTimeField(help_text="Timestamp of the most recent message in this conversation")
    
    # People involved in the conversation
    people_involved = models.ManyToManyField(Member, blank=True, related_name='discord_transcripts',
                                           help_text="Team members who participated in this conversation")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        # Fetch up to 4 participants to efficiently check if there are more than 3
        participants_list = list(self.people_involved.all()[:4])
        
        # Get names for the first 3 (or fewer)
        participant_names = [member.name for member in participants_list[:3]]
        
        if not participant_names:
            participants = "No participants"
        else:
            participants = ", ".join(participant_names)

        # Check if there were more than 3 participants fetched
        if len(participants_list) > 3:
            participants += " and others"
        
        return f"#{self.channel_name} ({self.get_channel_type_display()}) - {participants}"
    
    class Meta:
        ordering = ['-timestamp', '-created_at']


class SpaceConfiguration(models.Model):
    """Configuration for mapping data sources to Mantis spaces."""
    
    # Configuration types
    DATA_SOURCE_CHOICES = [
        ('github_issues', 'GitHub Issues'),
        ('panopto_meetings', 'Panopto Meetings'),
        ('discord_transcripts', 'Discord Transcripts'),
    ]
    
    # Basic info
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="Descriptive name for this configuration")
    data_source = models.CharField(max_length=50, choices=DATA_SOURCE_CHOICES, 
                                  help_text="Type of data source")
    active = models.BooleanField(default=True, help_text="Whether this configuration is active")
    
    # Space mapping
    space_id = models.CharField(max_length=100, help_text="Target Mantis space ID")
    space_name = models.CharField(max_length=200, blank=True, 
                                 help_text="Display name for the space (optional)")
    space_url = models.URLField(blank=True, help_text="URL to the Mantis space")
    
    # Source-specific configuration
    source_identifier = models.CharField(max_length=500, 
                                       help_text="Source identifier (e.g., GitHub repo, Panopto folder ID)")
    
    # Additional settings stored as JSON
    settings = models.JSONField(default=dict, blank=True, 
                               help_text="Additional configuration settings")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=100, blank=True, 
                                 help_text="User who created this configuration")
    
    def __str__(self):
        source_display = dict(self.DATA_SOURCE_CHOICES).get(self.data_source, self.data_source)
        return f"{source_display}: {self.name} -> {self.space_id}"
    
    class Meta:
        ordering = ['data_source', 'name']
        unique_together = ['data_source', 'source_identifier']