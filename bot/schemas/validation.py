from pydantic import BaseModel, Field, field_validator, ValidationError

class AmountModel(BaseModel):
    amount: float = Field(gt=0, description="Positive amount")
    
    @field_validator('amount', mode='before')
    def parse_float(cls, v):
        if isinstance(v, str):
            # Replace common separators
            v = v.replace(',', '.').replace(' ', '')
        return float(v)

class DayOfMonthModel(BaseModel):
    day: int = Field(ge=1, le=31, description="Day of month (1-31)")
    
    @field_validator('day', mode='before')
    def parse_int(cls, v):
        if isinstance(v, str):
             assert v.isdigit(), "Must be a number"
        return int(v)

class PhoneModel(BaseModel):
    phone: str = Field(pattern=r'^\+?[\d\s-]{10,20}$')
