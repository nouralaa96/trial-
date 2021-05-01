package levelset_Main;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.testng.Assert;

import actions.UIActions;

public class Create_Document_Page { 
	//variables
    private final WebDriver drivercreate   ;  
    
    // Constructor method 
      public Create_Document_Page(WebDriver driver1) {

       this.drivercreate = driver1 ;
    }      
      
      UIActions UIobject ;
   // locators    
        //  public String documentname = "20-Day Preliminary Notice" ; 
        //div[text()=20-Day Preliminary Notice]/..//span[text()=Free] 
        //span[text()="19"]/../span[text()="Free"] 
       // public  By day20 = By.xpath ("/html/body/div[3]/div/div/div[2]/div/div/div/div[1]/div[4]/div[1]/div/div[2]/span/span[2]" ) ;
      //  public  By day20 = By.xpath("//div[text()='documentname']/..//span[text()='Free']");
        public  By second =By.xpath("//div[text()=\"Notice of Intent to Lien\"]/..//span[text()=\"Free\"] "); 
        public By thrid =By.xpath("//div[text()=\"Lien / Bond Claim\"]/..//span[text()=\"$349\"] "); 
        public  By fourth = By.xpath("//div[text()=\"Notice of Intent to Lien\"]/..//span[text()=\"Free\"] "); 
        public  By click1 =By .xpath("//div[@class='title' and  text()='20-Day Preliminary Notice'] ") ;
      //keyword  
      public  void vaildate_DayPreliminaryNotices(String documentname ) {
    	/* 
     // String res1 =drivercreate.findElement(By.xpath("//div[text()='"+documentname+"']/..//span[text()='Free']")).getText() ;  
  	  By day20  = By.xpath("//div[text()='"+documentname+"']/..//span[text()='Free']" );
    	  //String res1 =drivercreate.findElement(By.xpath("//div[text()='"+documentname+"']/..//span[text()='Free']")).getText() ;
    	  String res1 =drivercreate.findElement(day20).getText() ;  
    	    return res1 ;  */  
    	  By day20  = By.xpath("//div[text()='"+documentname+"']/..//span[text()='Free']" ); 
    	    String locator ="//div[text()='"+documentname+"']/..//span[text()='Free']" ;
    	     String locator1 = "//div[@class=\"title\"] " ;
    	  UIobject	 =   new UIActions() ; 
    	  UIobject.click(day20);
    	 // UIobject.search_forDocumentInSearchBar(documentname);
    	  
    	//  Assert.assertEquals(UIobject.get_text("//div[@class=\"product-title-container card-header\"]/div[text()=\"Non-Required GC 20-Day Preliminary Notice (Public)\"]", "Xpath"),"Non-Required GC 20-Day Preliminary Notice (Public)") ;                                  
    	
    	  Assert.assertEquals( UIobject.get_text(locator , "Xpath"),"Free" ) ;
    	  Assert.assertEquals(UIobject.get_text(locator1,  "Xpath"),documentname );  
    	          
      } 
  /*    public  String get0_DayPreliminaryNoticestringclick1() { 
    	  drivercreate.findElement(day20).click();
    	  String res1 = drivercreate.findElement(click1).getText();
	      	return res1; 
    	  
      }*/
      
      public  void vaildate0_NoticeofIntenttoLien() { 
     	 
    	 /* String res1 =drivercreate.findElement(second).getText() ;
    	   drivercreate.findElement(second).click();
    	    return res1 ; */  
    	   String locator = " //div[text()=\\\"Notice of Intent to Lien\\\"]/..//span[text()=\\\"Free\\\"] "; 
    	  UIobject.click(second);      // try once by By class
     Assert.assertEquals( UIobject.get_text(locator, "Xpath"),"Free" ) ;  
                                                   // divide BY to two parametrs locator the  xpath as string
    	                                           // and Xpath word as type of loactor .
    	 
      } 
      public  String get0_NLienBondClaim() { 
      	 
    	  String res1 =drivercreate.findElement(thrid).getText() ;  
    	  drivercreate.findElement(thrid).click();
    	    return res1 ;
      }
      public  String get0_LienWaiver(){ 
       	 
    	  String res1 =drivercreate.findElement(fourth).getText() ;   
    	  drivercreate.findElement(fourth).click();
    	    return res1 ;
      }
}  


